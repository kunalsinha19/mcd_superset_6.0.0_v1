(globalThis.webpackChunksuperset=globalThis.webpackChunksuperset||[]).push([[7094],{19049:(e,t,n)=>{var r=n(79920)("capitalize",n(14792),n(96493));r.placeholder=n(2874),e.exports=r},68793:(e,t,n)=>{"use strict";n.r(t),n.d(t,{default:()=>$});var r,i=n(19049),o=n.n(i),a=n(2445),l=n(50290),c=n(17437),s=n(79378),u=n(74098),d=n(4651),h=n(42566),m=n(65729),p=n(8558),g=n(76576),f=n(88217),A=n(17355),y=n(96540),Y=n(32064);!function(e){e[e.AuthOID=0]="AuthOID",e[e.AuthDB=1]="AuthDB",e[e.AuthLDAP=2]="AuthLDAP",e[e.AuthOauth=4]="AuthOauth"}(r||(r={}));const b=(0,l.I4)(d.Z)`
  ${({theme:e})=>c.AH`
    max-width: 400px;
    width: 100%;
    margin-top: ${e.marginXL}px;
    color: ${e.colorBgContainer};
    background: ${e.colorBgBase};
    .ant-form-item-label label {
      color: ${e.colorPrimary};
    }
  `}
`,w=(0,l.I4)(h.o.Text)`
  ${({theme:e})=>c.AH`
    font-size: ${e.fontSizeSM}px;
  `}
`;function $(){const[e]=m.l.useForm(),[t,n]=(0,y.useState)(!1),i=(0,Y.Ay)(),l=(0,y.useMemo)((()=>{try{return new URLSearchParams(window.location.search).get("next")||""}catch(e){return""}}),[]),d=(0,y.useMemo)((()=>l?`/login/?next=${encodeURIComponent(l)}`:"/login/"),[l]),$=e=>{const t=`/login/${e}`;return l?`${t}${t.includes("?")?"&":"?"}next=${encodeURIComponent(l)}`:t},D=i.common.conf.AUTH_TYPE,x=i.common.conf.AUTH_PROVIDERS,I=i.common.conf.AUTH_USER_REGISTRATION,F=e=>{if(!e||"string"!=typeof e)return;const t=`${o()(e)}Outlined`,n=p.F[t];return n&&"function"==typeof n?(0,a.Y)(n,{}):void 0};return(0,a.Y)(g.s,{justify:"center",align:"center","data-test":"login-form",css:c.AH`
        width: 100%;
        height: calc(100vh - 200px);
      `,children:(0,a.FD)(b,{title:(0,u.t)("Sign in"),padded:!0,children:[D===r.AuthOID&&(0,a.Y)(g.s,{justify:"center",vertical:!0,gap:"middle",children:(0,a.Y)(m.l,{layout:"vertical",requiredMark:"optional",form:e,children:x.map((e=>(0,a.Y)(m.l.Item,{children:(0,a.FD)(f.$,{href:$(e.name),block:!0,iconPosition:"start",icon:F(e.name),children:[(0,u.t)("Sign in with")," ",o()(e.name)]})})))})}),D===r.AuthOauth&&(0,a.Y)(g.s,{justify:"center",gap:0,vertical:!0,children:(0,a.Y)(m.l,{layout:"vertical",requiredMark:"optional",form:e,children:x.map((e=>(0,a.Y)(m.l.Item,{children:(0,a.FD)(f.$,{href:$(e.name),block:!0,iconPosition:"start",icon:F(e.name),children:[(0,u.t)("Sign in with")," ",o()(e.name)]})})))})}),(D===r.AuthDB||D===r.AuthLDAP)&&(0,a.FD)(g.s,{justify:"center",vertical:!0,gap:"middle",children:[(0,a.Y)(h.o.Text,{type:"secondary",children:(0,u.t)("Enter your login and password below:")}),(0,a.FD)(m.l,{layout:"vertical",requiredMark:"optional",form:e,onFinish:e=>{n(!0),s.A.postForm(d,e,"").finally((()=>{n(!1)}))},children:[(0,a.Y)(m.l.Item,{label:(0,a.Y)(w,{children:(0,u.t)("Username:")}),name:"username",rules:[{required:!0,message:(0,u.t)("Please enter your username")}],children:(0,a.Y)(A.A,{autoFocus:!0,prefix:(0,a.Y)(p.F.UserOutlined,{iconSize:"l"}),"data-test":"username-input"})}),(0,a.Y)(m.l.Item,{label:(0,a.Y)(w,{children:(0,u.t)("Password:")}),name:"password",rules:[{required:!0,message:(0,u.t)("Please enter your password")}],children:(0,a.Y)(A.A.Password,{prefix:(0,a.Y)(p.F.KeyOutlined,{iconSize:"l"}),"data-test":"password-input"})}),(0,a.Y)(m.l.Item,{label:null,children:(0,a.FD)(g.s,{css:c.AH`
                    width: 100%;
                  `,children:[(0,a.Y)(f.$,{block:!0,type:"primary",htmlType:"submit",loading:t,"data-test":"login-button",children:(0,u.t)("Sign in")}),I&&(0,a.Y)(f.$,{block:!0,type:"default",href:"/register/","data-test":"register-button",children:(0,u.t)("Register")})]})})]})]})]})})}},96493:e=>{e.exports={cap:!1,curry:!1,fixed:!1,immutable:!1,rearg:!1}}}]);