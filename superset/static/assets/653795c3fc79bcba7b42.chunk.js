"use strict";(globalThis.webpackChunksuperset=globalThis.webpackChunksuperset||[]).push([[6830],{8883:(e,t,n)=>{n.r(t),n.d(t,{UserInfo:()=>x,default:()=>$});var a=n(2445),r=n(96540),s=n(50290),i=n(17437),o=n(79378),l=n(74098),d=n(20237),c=n(64457),u=n(55957),m=n(82384),p=n(17355),h=n(30613),w=n(60158);function f({show:e,onHide:t,onSave:n,isEditMode:r,user:s}){const{addDangerToast:i,addSuccessToast:d}=(0,c.Yf)(),u=r?["first_name","last_name"]:["password","confirm_password"],f=r?{first_name:null==s?void 0:s.firstName,last_name:null==s?void 0:s.lastName}:{};return(0,a.Y)(h.k,{show:e,onHide:t,title:r?(0,l.t)("Edit user"):(0,l.t)("Reset password"),onSave:n,formSubmitHandler:async e=>{try{const{confirm_password:t,...a}=e;await o.A.put({endpoint:"/api/v1/me/",jsonPayload:await(0,w.YC)({...a})}),d(r?(0,l.t)("The user was updated successfully"):(0,l.t)("The password reset was successful")),n()}catch(e){i((0,l.t)("Something went wrong while saving the user info"))}},requiredFields:u,initialValues:f,children:r?(0,a.Y)((()=>(0,a.FD)(a.FK,{children:[(0,a.Y)(m.e,{name:"first_name",label:(0,l.t)("First name"),rules:[{required:!0,message:(0,l.t)("First name is required")}],children:(0,a.Y)(p.A,{name:"first_name",placeholder:(0,l.t)("Enter the user's first name")})}),(0,a.Y)(m.e,{name:"last_name",label:(0,l.t)("Last name"),rules:[{required:!0,message:(0,l.t)("Last name is required")}],children:(0,a.Y)(p.A,{name:"last_name",placeholder:(0,l.t)("Enter the user's last name")})})]})),{}):(0,a.Y)((()=>(0,a.FD)(a.FK,{children:[(0,a.Y)(m.e,{name:"password",label:(0,l.t)("Password"),rules:[{required:!0,message:(0,l.t)("Password is required")}],children:(0,a.Y)(p.A,{type:"password",name:"password",placeholder:"Enter the user's password"})}),(0,a.Y)(m.e,{name:"confirm_password",label:(0,l.t)("Confirm Password"),dependencies:["password"],rules:[{required:!0,message:(0,l.t)("Please confirm your password")},({getFieldValue:e})=>({validator:(t,n)=>n&&e("password")!==n?Promise.reject(new Error((0,l.t)("Passwords do not match!"))):Promise.resolve()})],children:(0,a.Y)(p.A,{type:"password",name:"confirm_password",placeholder:(0,l.t)("Confirm the user's password")})})]})),{})})}const g=e=>(0,a.Y)(f,{...e,isEditMode:!1}),y=e=>(0,a.Y)(f,{...e,isEditMode:!0});var b=n(8558),v=n(43303);const Y=s.I4.div`
  ${({theme:e})=>i.AH`
    font-weight: ${e.fontWeightStrong};
    text-align: left;
    font-size: 18px;
    padding: ${3*e.sizeUnit}px;
    padding-left: ${7*e.sizeUnit}px;
    display: inline-block;
    line-height: ${9*e.sizeUnit}px;
    width: 100%;
    background-color: ${e.colorBgContainer};
    margin-bottom: ${6*e.sizeUnit}px;
  `}
`,S=s.I4.div`
  ${({theme:e})=>i.AH`
    margin: 0px ${3*e.sizeUnit}px ${6*e.sizeUnit}px
      ${3*e.sizeUnit}px;
    background-color: ${e.colorBgContainer};
  `}
`,A=s.I4.div`
  ${({theme:e})=>i.AH`
    .ant-row {
      margin: 0px ${3*e.sizeUnit}px ${6*e.sizeUnit}px
        ${3*e.sizeUnit}px;
    }
    && .menu > .ant-menu {
      padding: 0px;
    }
    && .nav-right {
      left: 0;
      padding-left: ${4*e.sizeUnit}px;
      position: relative;
      height: ${15*e.sizeUnit}px;
    }
  `}
`,F=s.I4.span`
  font-weight: ${({theme:e})=>e.fontWeightStrong};
`;var C;function x({user:e}){const t=(0,s.DP)(),[n,m]=(0,r.useState)({resetPassword:!1,edit:!1}),p=e=>m((t=>({...t,[e]:!0}))),h=e=>m((t=>({...t,[e]:!1}))),{addDangerToast:w}=(0,c.Yf)(),[f,x]=(0,r.useState)(e);(0,r.useEffect)((()=>{$()}),[]);const $=(0,r.useCallback)((()=>{o.A.get({endpoint:"/api/v1/me/"}).then((({json:e})=>{const t={...e.result,firstName:e.result.first_name,lastName:e.result.last_name};x(t)})).catch((e=>{w("Failed to fetch user info:",e)}))}),[f]),k=[{name:(0,a.FD)(a.FK,{children:[(0,a.Y)(b.F.LockOutlined,{iconColor:t.colorPrimary,iconSize:"m",css:i.AH`
              margin: auto ${2*t.sizeUnit}px auto 0;
              vertical-align: text-top;
            `}),(0,l.t)("Reset my password")]}),buttonStyle:"secondary",onClick:()=>{p(C.ResetPassword)},"data-test":"reset-password-button"},{name:(0,a.FD)(a.FK,{children:[(0,a.Y)(b.F.FormOutlined,{iconSize:"m",css:i.AH`
              margin: auto ${2*t.sizeUnit}px auto 0;
              vertical-align: text-top;
            `}),(0,l.t)("Edit user")]}),buttonStyle:"primary",onClick:()=>{p(C.Edit)},"data-test":"edit-user-button"}];return(0,a.FD)(A,{children:[(0,a.Y)(Y,{children:"Your user information"}),(0,a.Y)(S,{children:(0,a.FD)(v.S,{defaultActiveKey:["userInfo","personalInfo"],ghost:!0,children:[(0,a.Y)(v.S.Panel,{header:(0,a.Y)(F,{children:"User info"}),children:(0,a.FD)(u.A,{bordered:!0,size:"small",column:1,labelStyle:{width:"120px"},children:[(0,a.Y)(u.A.Item,{label:"User Name",children:e.username}),(0,a.Y)(u.A.Item,{label:"Is Active?",children:e.isActive?"Yes":"No"}),(0,a.Y)(u.A.Item,{label:"Role",children:e.roles?Object.keys(e.roles).join(", "):"None"}),(0,a.Y)(u.A.Item,{label:"Login count",children:e.loginCount})]})},"userInfo"),(0,a.Y)(v.S.Panel,{header:(0,a.Y)(F,{children:"Personal info"}),children:(0,a.FD)(u.A,{bordered:!0,size:"small",column:1,labelStyle:{width:"120px"},children:[(0,a.Y)(u.A.Item,{label:"First Name",children:f.firstName}),(0,a.Y)(u.A.Item,{label:"Last Name",children:f.lastName}),(0,a.Y)(u.A.Item,{label:"Email",children:e.email})]})},"personalInfo")]})}),n.resetPassword&&(0,a.Y)(g,{onHide:()=>h(C.ResetPassword),show:n.resetPassword,onSave:()=>{h(C.ResetPassword)}}),n.edit&&(0,a.Y)(y,{onHide:()=>h(C.Edit),show:n.edit,onSave:()=>{h(C.Edit),$()},user:f}),(0,a.Y)(d.A,{buttons:k})]})}!function(e){e.ResetPassword="resetPassword",e.Edit="edit"}(C||(C={}));const $=x},30613:(e,t,n)=>{n.d(t,{k:()=>d});var a=n(2445),r=n(96540),s=n(74098),i=n(88217),o=n(65729),l=n(97163);function d({show:e,onHide:t,title:n,onSave:d,children:c,initialValues:u={},formSubmitHandler:m,bodyStyle:p={},requiredFields:h=[],name:w}){const[f]=o.l.useForm(),[g,y]=(0,r.useState)(!1),b=(0,r.useCallback)((()=>{f.resetFields(),y(!1)}),[f]),[v,Y]=(0,r.useState)(!0),S=(0,r.useCallback)((()=>{b(),t()}),[t,b]),A=(0,r.useCallback)((()=>{b(),d()}),[d,b]),F=(0,r.useCallback)((async e=>{try{y(!0),await m(e),A()}catch(e){console.error(e)}finally{y(!1)}}),[m,A]),C=()=>{const e=f.getFieldsError().some((({errors:e})=>e.length)),t=f.getFieldsValue(),n=h.some((e=>!t[e]));Y(e||n)};return(0,a.Y)(l.aF,{name:w,show:e,title:n,onHide:S,bodyStyle:p,footer:(0,a.FD)(a.FK,{children:[(0,a.Y)(i.$,{buttonStyle:"secondary","data-test":"modal-cancel-button",onClick:S,children:(0,s.t)("Cancel")}),(0,a.Y)(i.$,{buttonStyle:"primary",htmlType:"submit",onClick:()=>f.submit(),"data-test":"form-modal-save-button",disabled:g||v,children:g?(0,s.t)("Saving..."):(0,s.t)("Save")})]}),children:(0,a.Y)(o.l,{form:f,layout:"vertical",onFinish:F,initialValues:u,onValuesChange:C,onFieldsChange:C,children:"function"==typeof c?c(f):c})})}},60158:(e,t,n)=>{n.d(t,{TW:()=>i,Xk:()=>o,YC:()=>l});var a=n(79378);const r="superset-login-msg-v1";function s(e){const t=e instanceof Uint8Array?e:new Uint8Array(e);let n="";return t.forEach((e=>{n+=String.fromCharCode(e)})),btoa(n).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"")}function i(){return"undefined"!=typeof window&&!!window.crypto&&!!window.crypto.subtle&&"undefined"!=typeof TextEncoder}async function o(e,t,n){const{subtle:a}=window.crypto,i=new TextEncoder,o={name:"ECDH",namedCurve:"P-256"},l=await a.importKey("raw",function(e){const t=e.replace(/-/g,"+").replace(/_/g,"/"),n=atob(t+"=".repeat((4-t.length%4)%4)),a=new Uint8Array(n.length);for(let e=0;e<n.length;e+=1)a[e]=n.charCodeAt(e);return a}(t),o,!1,[]),d=await a.generateKey(o,!0,["deriveBits"]),c=await a.deriveBits({name:"ECDH",public:l},d.privateKey,256),u=window.crypto.getRandomValues(new Uint8Array(16)),m=window.crypto.getRandomValues(new Uint8Array(12)),p=await a.importKey("raw",c,"HKDF",!1,["deriveKey"]),h=await a.deriveKey({name:"HKDF",hash:"SHA-256",salt:u,info:i.encode(r)},p,{name:"AES-GCM",length:256},!1,["encrypt"]),w=await a.encrypt({name:"AES-GCM",iv:m},h,i.encode(JSON.stringify({p:e,n})));return["v1",s(await a.exportKey("raw",d.publicKey)),s(u),s(m),s(w)].join(".")}async function l(e){const{password:t,...n}=e;if("string"!=typeof t||!t||!i())return e;try{const{json:r}=await a.A.get({endpoint:"/api/v1/me/password_key"}),{key:s,nonce:i}=r.result||{};return s&&i?{...n,enc_password:await o(t,s,i)}:e}catch(t){return e}}}}]);