/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import { SupersetClient, styled, t, css } from '@superset-ui/core';
import {
  Button,
  Card,
  Flex,
  Form,
  Input,
  Typography,
  Icons,
} from '@superset-ui/core/components';
import { useState, useMemo, useEffect, useCallback } from 'react';
import { capitalize } from 'lodash/fp';
import getBootstrapData from 'src/utils/getBootstrapData';

type OAuthProvider = {
  name: string;
  icon: string;
};

type OIDProvider = {
  name: string;
  url: string;
};

type Provider = OAuthProvider | OIDProvider;

interface LoginForm {
  username: string;
  password: string;
  captcha_answer: string;
}

enum AuthType {
  AuthOID = 0,
  AuthDB = 1,
  AuthLDAP = 2,
  AuthOauth = 4,
}

const StyledCard = styled(Card)`
  ${({ theme }) => css`
    max-width: 400px;
    width: 100%;
    margin-top: ${theme.marginXL}px;
    color: ${theme.colorBgContainer};
    background: ${theme.colorBgBase};
    .ant-form-item-label label {
      color: ${theme.colorPrimary};
    }
  `}
`;

const StyledLabel = styled(Typography.Text)`
  ${({ theme }) => css`
    font-size: ${theme.fontSizeSM}px;
  `}
`;

// Max 3 failed attempts, then the password field freezes with a visible
// countdown until Flask-Limiter's own AUTH_RATE_LIMIT window resets (see
// superset_config.py.example) -- persisted to sessionStorage so a page
// refresh mid-lockout doesn't just reset the visible timer (the server-side
// limit isn't affected either way; this only keeps the UI honest).
const LOCKOUT_STORAGE_KEY = 'superset_login_locked_until';
const DEFAULT_LOCKOUT_SECONDS = 60;

function readStoredLockout(): number | null {
  try {
    const stored = window.sessionStorage.getItem(LOCKOUT_STORAGE_KEY);
    const parsed = stored ? Number.parseInt(stored, 10) : NaN;
    return Number.isFinite(parsed) && parsed > Date.now() ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function persistLockout(until: number | null) {
  try {
    if (until) {
      window.sessionStorage.setItem(LOCKOUT_STORAGE_KEY, String(until));
    } else {
      window.sessionStorage.removeItem(LOCKOUT_STORAGE_KEY);
    }
  } catch (_error) {
    // Private browsing / storage disabled -- the countdown just won't
    // survive a refresh, enforcement itself is still server-side.
  }
}

export default function Login() {
  const [form] = Form.useForm<LoginForm>();
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [lockedUntil, setLockedUntil] = useState<number | null>(
    readStoredLockout,
  );
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  // Audit finding #11 -- self-hosted CAPTCHA (see
  // superset/security/login_captcha.py for why not RecaptchaField).
  // Alphanumeric per the audit team's follow-up instruction (a plain
  // arithmetic sum was too small an answer space); validated server-side
  // on submit, matched case-insensitively.
  const [captchaCode, setCaptchaCode] = useState<string>('');

  const fetchCaptcha = useCallback(() => {
    fetch('/login/captcha', { credentials: 'same-origin' })
      .then(res => (res.ok ? res.json() : Promise.reject(res)))
      .then(data => setCaptchaCode(data.code))
      .catch(() => setCaptchaCode(''));
  }, []);

  useEffect(() => {
    fetchCaptcha();
  }, [fetchCaptcha]);

  useEffect(() => {
    if (!lockedUntil) {
      setRemainingSeconds(0);
      return undefined;
    }
    const tick = () => {
      const secondsLeft = Math.max(
        0,
        Math.ceil((lockedUntil - Date.now()) / 1000),
      );
      setRemainingSeconds(secondsLeft);
      if (secondsLeft <= 0) {
        setLockedUntil(null);
        persistLockout(null);
        setErrorMessage('');
        fetchCaptcha();
      }
    };
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [lockedUntil, fetchCaptcha]);

  const bootstrapData = getBootstrapData();
  const nextUrl = useMemo(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get('next') || '';
    } catch (_error) {
      return '';
    }
  }, []);

  const loginEndpoint = useMemo(
    () => (nextUrl ? `/login/?next=${encodeURIComponent(nextUrl)}` : '/login/'),
    [nextUrl],
  );

  const buildProviderLoginUrl = (providerName: string) => {
    const base = `/login/${providerName}`;
    return nextUrl
      ? `${base}${base.includes('?') ? '&' : '?'}next=${encodeURIComponent(nextUrl)}`
      : base;
  };

  const authType: AuthType = bootstrapData.common.conf.AUTH_TYPE;
  const providers: Provider[] = bootstrapData.common.conf.AUTH_PROVIDERS;
  const authRegistration: boolean =
    bootstrapData.common.conf.AUTH_USER_REGISTRATION;

  const onFinish = async (values: LoginForm) => {
    if (lockedUntil && lockedUntil > Date.now()) {
      return;
    }
    setLoading(true);
    setErrorMessage('');
    try {
      const { json } = await SupersetClient.post({
        endpoint: loginEndpoint,
        jsonPayload: values,
      });
      window.location.href = json?.redirect || '/';
      // Intentionally leave loading=true -- the page is navigating away.
    } catch (err: any) {
      if (err?.status === 429) {
        const retryAfterHeader = err.headers?.get?.('Retry-After');
        const retryAfterSeconds =
          Number.parseInt(retryAfterHeader, 10) || DEFAULT_LOCKOUT_SECONDS;
        const until = Date.now() + retryAfterSeconds * 1000;
        setLockedUntil(until);
        persistLockout(until);
        setErrorMessage(
          t('Too many failed attempts. Please wait for the timer to finish.'),
        );
      } else {
        let message = t(
          'Invalid username, password, or security check answer.',
        );
        try {
          const body = await err.json();
          if (body?.message) {
            message = body.message;
          }
        } catch (_parseError) {
          // Non-JSON error body -- keep the generic message above.
        }
        setErrorMessage(message);
      }
      form.setFieldsValue({ captcha_answer: '' } as Partial<LoginForm>);
      fetchCaptcha();
      setLoading(false);
    }
  };

  const getAuthIconElement = (
    providerName: string,
  ): React.JSX.Element | undefined => {
    if (!providerName || typeof providerName !== 'string') {
      return undefined;
    }
    const iconComponentName = `${capitalize(providerName)}Outlined`;
    const IconComponent = (Icons as Record<string, React.ComponentType<any>>)[
      iconComponentName
    ];

    if (IconComponent && typeof IconComponent === 'function') {
      return <IconComponent />;
    }
    return undefined;
  };

  return (
    <Flex
      justify="center"
      align="center"
      data-test="login-form"
      css={css`
        width: 100%;
        height: calc(100vh - 200px);
      `}
    >
      <StyledCard title={t('Sign in')} padded>
        {authType === AuthType.AuthOID && (
          <Flex justify="center" vertical gap="middle">
            <Form layout="vertical" requiredMark="optional" form={form}>
              {providers.map((provider: OIDProvider) => (
                <Form.Item<LoginForm>>
                  <Button
                    href={buildProviderLoginUrl(provider.name)}
                    block
                    iconPosition="start"
                    icon={getAuthIconElement(provider.name)}
                  >
                    {t('Sign in with')} {capitalize(provider.name)}
                  </Button>
                </Form.Item>
              ))}
            </Form>
          </Flex>
        )}
        {authType === AuthType.AuthOauth && (
          <Flex justify="center" gap={0} vertical>
            <Form layout="vertical" requiredMark="optional" form={form}>
              {providers.map((provider: OAuthProvider) => (
                <Form.Item<LoginForm>>
                  <Button
                    href={buildProviderLoginUrl(provider.name)}
                    block
                    iconPosition="start"
                    icon={getAuthIconElement(provider.name)}
                  >
                    {t('Sign in with')} {capitalize(provider.name)}
                  </Button>
                </Form.Item>
              ))}
            </Form>
          </Flex>
        )}

        {(authType === AuthType.AuthDB || authType === AuthType.AuthLDAP) && (
          <Flex justify="center" vertical gap="middle">
            <Typography.Text type="secondary">
              {t('Enter your login and password below:')}
            </Typography.Text>
            <Form
              layout="vertical"
              requiredMark="optional"
              form={form}
              onFinish={onFinish}
            >
              <Form.Item<LoginForm>
                label={<StyledLabel>{t('Username:')}</StyledLabel>}
                name="username"
                rules={[
                  { required: true, message: t('Please enter your username') },
                ]}
              >
                <Input
                  autoFocus
                  maxLength={64}
                  prefix={<Icons.UserOutlined iconSize="l" />}
                  data-test="username-input"
                />
              </Form.Item>
              <Form.Item<LoginForm>
                label={<StyledLabel>{t('Password:')}</StyledLabel>}
                name="password"
                rules={[
                  { required: true, message: t('Please enter your password') },
                ]}
              >
                <Input
                  type="password"
                  maxLength={128}
                  disabled={!!lockedUntil}
                  prefix={<Icons.KeyOutlined iconSize="l" />}
                  data-test="password-input"
                />
              </Form.Item>
              {lockedUntil ? (
                <Typography.Text type="danger" data-test="login-lockout-timer">
                  {t(
                    'Too many failed attempts. Try again in %s seconds.',
                    remainingSeconds,
                  )}
                </Typography.Text>
              ) : (
                errorMessage && (
                  <Typography.Text type="danger" data-test="login-error-message">
                    {errorMessage}
                  </Typography.Text>
                )
              )}
              {captchaCode && (
                <Form.Item<LoginForm>
                  label={
                    <StyledLabel>
                      {t('Security check: type the code %s', captchaCode)}
                    </StyledLabel>
                  }
                  name="captcha_answer"
                  rules={[
                    { required: true, message: t('Please answer the security check') },
                  ]}
                >
                  <Input
                    maxLength={6}
                    disabled={!!lockedUntil}
                    css={css`
                      text-transform: uppercase;
                    `}
                    data-test="captcha-answer-input"
                  />
                </Form.Item>
              )}
              <Form.Item label={null}>
                <Flex
                  css={css`
                    width: 100%;
                  `}
                >
                  <Button
                    block
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    disabled={!!lockedUntil}
                    data-test="login-button"
                  >
                    {t('Sign in')}
                  </Button>
                  {authRegistration && (
                    <Button
                      block
                      type="default"
                      href="/register/"
                      data-test="register-button"
                    >
                      {t('Register')}
                    </Button>
                  )}
                </Flex>
              </Form.Item>
            </Form>
          </Flex>
        )}
      </StyledCard>
    </Flex>
  );
}
