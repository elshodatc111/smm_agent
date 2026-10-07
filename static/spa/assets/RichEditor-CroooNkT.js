import{c as l,r as k,j as t,a6 as z,ag as E,q as H}from"./index-n0IZDaqS.js";/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=l("Bold",[["path",{d:"M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8",key:"mg9rjx"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const L=l("Code",[["polyline",{points:"16 18 22 12 16 6",key:"z7tu5w"}],["polyline",{points:"8 6 2 12 8 18",key:"1eg1df"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=l("Eraser",[["path",{d:"m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21",key:"182aya"}],["path",{d:"M22 21H7",key:"t4ddhn"}],["path",{d:"m5 11 9 9",key:"1mo9qw"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const F=l("Hash",[["line",{x1:"4",x2:"20",y1:"9",y2:"9",key:"4lhtct"}],["line",{x1:"4",x2:"20",y1:"15",y2:"15",key:"vyu0kd"}],["line",{x1:"10",x2:"8",y1:"3",y2:"21",key:"1ggp8o"}],["line",{x1:"16",x2:"14",y1:"3",y2:"21",key:"weycgp"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=l("Italic",[["line",{x1:"19",x2:"10",y1:"4",y2:"4",key:"15jd3p"}],["line",{x1:"14",x2:"5",y1:"20",y2:"20",key:"bu0au3"}],["line",{x1:"15",x2:"9",y1:"4",y2:"20",key:"uljnxc"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=l("Quote",[["path",{d:"M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z",key:"rib7q0"}],["path",{d:"M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z",key:"1ymkrd"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Q=l("SquareCode",[["path",{d:"M10 9.5 8 12l2 2.5",key:"3mjy60"}],["path",{d:"m14 9.5 2 2.5-2 2.5",key:"1bir2l"}],["rect",{width:"18",height:"18",x:"3",y:"3",rx:"2",key:"afitv7"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const U=l("Strikethrough",[["path",{d:"M16 4H9a3 3 0 0 0-2.83 4",key:"43sutm"}],["path",{d:"M14 12a4 4 0 0 1 0 8H6",key:"nlfj13"}],["line",{x1:"4",x2:"20",y1:"12",y2:"12",key:"1e0a9i"}]]);/**
 * @license lucide-react v0.454.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=l("Underline",[["path",{d:"M6 4v6a6 6 0 0 0 12 0V4",key:"9kb039"}],["line",{x1:"4",x2:"20",y1:"20",y2:"20",key:"nun2al"}]]);function B({value:o,onChange:y,rows:f=9,placeholder:v,id:j,className:w,richOk:p=!0}){const x=k.useRef(null),[c,r]=k.useState(null),d=(e,s=!1)=>{const n=x.current;if(!n)return;const i=n.selectionStart,b=n.selectionEnd,[g,h,K]=e(o.slice(i,b)),S=o.slice(0,i)+g+h+K+o.slice(b);y(S),requestAnimationFrame(()=>{n.focus();const u=i+g.length;n.setSelectionRange(u,u+h.length)})},a=(e,s="matn",n="")=>d(i=>[`<${e}${n}>`,i||s,`</${e}>`]),C=()=>d(e=>["",e.replace(/<\/?[a-zA-Z][^>]*>/g,""),""]),m=()=>{const e=(c||"").trim();/^(https?:\/\/|tg:\/\/|mailto:)/i.test(e)&&(a("a","havola matni",` href="${e.replace(/"/g,"&quot;")}"`),r(null))},q=e=>{if(!(e.ctrlKey||e.metaKey)||e.altKey)return;const s=e.key.toLowerCase(),n={b:()=>a("b"),i:()=>a("i"),u:()=>a("u"),k:()=>r("https://")};e.shiftKey&&s==="s"?(e.preventDefault(),a("s")):!e.shiftKey&&n[s]&&(e.preventDefault(),n[s]())},N=[["Qalin (Ctrl+B)",M,()=>a("b"),"b"],["Yotiq (Ctrl+I)",I,()=>a("i"),"i"],["Tagiga chizilgan (Ctrl+U)",V,()=>a("u"),"u"],["Ustiga chizilgan (Ctrl+Shift+S)",U,()=>a("s"),"s"],["Havola (Ctrl+K)",z,()=>r("https://"),"a"],["Kod",L,()=>a("code"),"c"],["Kod bloki",Q,()=>a("pre"),"p"],["Iqtibos",R,()=>a("blockquote"),"q"],["Spoyler (yashirin matn)",E,()=>a("tg-spoiler"),"sp"]];return t.jsxs("div",{className:H("rounded-lg border border-line bg-surface focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20 transition",w),children:[t.jsxs("div",{className:"flex flex-wrap items-center gap-0.5 px-1.5 py-1 border-b border-line bg-surface2/60 rounded-t-lg",children:[N.map(([e,s,n,i])=>t.jsx("button",{type:"button",title:e,"aria-label":e,onClick:n,disabled:!p,className:"w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface transition disabled:opacity-40",children:t.jsx(s,{className:"w-4 h-4"})},i)),t.jsx("span",{className:"w-px h-5 bg-line mx-1"}),t.jsx("button",{type:"button",title:"Hashtag qo'shish","aria-label":"Hashtag",onClick:()=>d(e=>["#",e,""]),className:"w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface",children:t.jsx(F,{className:"w-4 h-4"})}),t.jsx("button",{type:"button",title:"Formatlashni tozalash","aria-label":"Formatlashni tozalash",onClick:C,className:"w-8 h-8 grid place-items-center rounded-md text-muted hover:text-fg hover:bg-surface",children:t.jsx(D,{className:"w-4 h-4"})}),t.jsx("span",{className:"ml-auto text-[11.5px] text-muted pr-1.5 hidden sm:block",children:p?"Telegram: teglar saqlanadi":"Faqat Telegram formatlashni qo'llaydi"})]}),c!==null&&t.jsxs("div",{className:"flex items-center gap-2 px-2 py-1.5 border-b border-line",children:[t.jsx("input",{autoFocus:!0,className:"input h-8",value:c,onChange:e=>r(e.target.value),placeholder:"https://…",onKeyDown:e=>{e.key==="Enter"&&(e.preventDefault(),m()),e.key==="Escape"&&r(null)}}),t.jsx("button",{type:"button",className:"btn btn-primary btn-sm",onClick:m,children:"Qo'yish"}),t.jsx("button",{type:"button",className:"btn btn-sm",onClick:()=>r(null),children:"×"})]}),t.jsx("textarea",{ref:x,id:j,rows:f,value:o,placeholder:v,onChange:e=>y(e.target.value),onKeyDown:q,className:"w-full resize-y bg-transparent px-3 py-2.5 text-[14px] leading-relaxed outline-none placeholder:text-muted/70 rounded-b-lg"})]})}export{B as R};
