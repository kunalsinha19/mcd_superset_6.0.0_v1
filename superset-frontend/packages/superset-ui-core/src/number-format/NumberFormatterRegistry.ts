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
import { FormatLocaleDefinition } from 'd3-format';
import { RegistryWithDefaultKey, OverwritePolicy } from '../models';
import { DEFAULT_D3_FORMAT } from './D3FormatConfig';
import createD3NumberFormatter from './factories/createD3NumberFormatter';
import createSmartNumberFormatter from './factories/createSmartNumberFormatter';
import NumberFormats from './NumberFormats';
import NumberFormatter from './NumberFormatter';

export default class NumberFormatterRegistry extends RegistryWithDefaultKey<
  NumberFormatter,
  NumberFormatter
> {
  d3Format: FormatLocaleDefinition;

  constructor() {
    super({
      name: 'NumberFormatter',
      overwritePolicy: OverwritePolicy.Warn,
    });

    this.registerValue(
      NumberFormats.SMART_NUMBER,
      createSmartNumberFormatter(),
    );
    this.registerValue(
      NumberFormats.SMART_NUMBER_SIGNED,
      createSmartNumberFormatter({ signed: true }),
    );
    this.setDefaultKey(NumberFormats.SMART_NUMBER);
    this.d3Format = DEFAULT_D3_FORMAT;
  }

  setD3Format(d3Format: Partial<FormatLocaleDefinition>) {
    this.d3Format = { ...DEFAULT_D3_FORMAT, ...d3Format };
    return this;
  }

  get(formatterId?: string) {
    const targetFormat = `${
      formatterId === null ||
      typeof formatterId === 'undefined' ||
      formatterId === ''
        ? this.defaultKey
        : formatterId
    }`.trim();

    if (this.has(targetFormat)) {
      return super.get(targetFormat) as NumberFormatter;
    }

    // Indian number format handler
    if (targetFormat === 'FM99,99,99,999') {
      const indianFormatter = new NumberFormatter({
        id: targetFormat,
        label: 'Indian Format',
        formatFunc: (value: number) => {
          if (value === null || value === undefined || Number.isNaN(value)) {
            return String(value);
          }
          const isNegative = value < 0;
          const absValue = Math.abs(Math.round(value));
          const str = String(absValue);
          let result = '';
          if (str.length <= 3) {
            result = str;
          } else {
            const last3 = str.slice(-3);
            const remaining = str.slice(0, -3);
            result = remaining.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3;
          }
          return isNegative ? '-' + result : result;
        },
      });
      this.registerValue(targetFormat, indianFormatter);
      return indianFormatter;
    }

    // Indian K/L/Cr format handler
    if (targetFormat === 'INDIAN_K_L_CR') {
      const indianKLCrFormatter = new NumberFormatter({
        id: targetFormat,
        label: 'Indian K/L/Cr',
        formatFunc: (value: number) => {
          if (value === null || value === undefined || Number.isNaN(value)) {
            return String(value);
          }
          const isNegative = value < 0;
          const absValue = Math.abs(value);
          let result = '';
          if (absValue >= 10000000) {
            result = `${(absValue / 10000000).toFixed(2)} Cr`;
          } else if (absValue >= 100000) {
            result = `${(absValue / 100000).toFixed(2)} L`;
          } else if (absValue >= 1000) {
            result = `${(absValue / 1000).toFixed(2)} K`;
          } else {
            result = absValue.toFixed(2);
          }
          return isNegative ? '-' + result : result;
        },
      });
      this.registerValue(targetFormat, indianKLCrFormatter);
      return indianKLCrFormatter;
    }

    // Create new formatter if does not exist
    const formatter = createD3NumberFormatter({
      formatString: targetFormat,
      locale: this.d3Format,
    });
    this.registerValue(targetFormat, formatter);

    return formatter;
  }

  format(
    formatterId: string | undefined,
    value: number | null | undefined,
  ): string {
    return this.get(formatterId)(value);
  }
}
