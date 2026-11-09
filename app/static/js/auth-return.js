'use strict';
// Pure parser shared by the browser and regression tests. Never logs token values.
function parseAuthReturn(fragment) {
 const p=new URLSearchParams(fragment.replace(/^#/,''));
 if(p.has('error')||p.has('error_code'))return {kind:'error',message:'This confirmation link is invalid or has expired. If you already confirmed your email, sign in instead.'};
 const access=p.get('access_token'),refresh=p.get('refresh_token');
 if(access&&refresh){
  if(p.get('type')==='recovery')return {kind:'error',message:'Use the password recovery flow to update your password before signing in.'};
  if(p.get('token_type')&&p.get('token_type').toLowerCase()!=='bearer')return {kind:'error',message:'Unsupported confirmation response. Please sign in.'};
  return {kind:'session',session:{access_token:access,refresh_token:refresh,token_type:'bearer'}};
 }
 if(p.has('access_token')||p.has('refresh_token'))return {kind:'error',message:'The confirmation response was incomplete. Please sign in.'};
 return {kind:'none'};
}
if(typeof module!=='undefined')module.exports={parseAuthReturn};
