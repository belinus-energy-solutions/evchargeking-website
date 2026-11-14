/* Preview lock. Every page and the shop's script and catalogue are encrypted with the preview password
   (AES-256-GCM, key derived with PBKDF2). Nothing readable is served until the right password is entered.
   The derived key is remembered in this browser so the visitor is asked once. Removed at go-live. */
(function(){
  var C=window.__GATE, DATA=document.getElementById("gate-data").textContent.trim(), K="evck-preview-key-"+C.salt.slice(0,8), TXT={
    en:{h:"Preview",p:"This preview of the new EVChargeking website is protected. Enter the password to continue.",l:"Password",b:"Open preview",e:"That password is not correct."},
    nl:{h:"Preview",p:"Deze preview van de nieuwe EVChargeking-website is beveiligd. Geef het wachtwoord in om verder te gaan.",l:"Wachtwoord",b:"Preview openen",e:"Dat wachtwoord klopt niet."},
    fr:{h:"Aperçu",p:"Cet aperçu du nouveau site EVChargeking est protégé. Saisissez le mot de passe pour continuer.",l:"Mot de passe",b:"Ouvrir l’aperçu",e:"Ce mot de passe n’est pas correct."}};
  var T=TXT[document.documentElement.lang]||TXT.en, sub=window.crypto&&crypto.subtle;
  function b64(s){var b=atob(s),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a;}
  function toB64(a){var s="";a=new Uint8Array(a);for(var i=0;i<a.length;i++)s+=String.fromCharCode(a[i]);return btoa(s);}
  function derive(pw){return sub.importKey("raw",new TextEncoder().encode(pw),"PBKDF2",false,["deriveBits"]).then(function(k){
    return sub.deriveBits({name:"PBKDF2",hash:"SHA-256",salt:b64(C.salt),iterations:C.iter},k,256);});}
  function dec(raw,data){var d=b64(data);return sub.importKey("raw",raw,"AES-GCM",false,["decrypt"]).then(function(k){
    return sub.decrypt({name:"AES-GCM",iv:d.slice(0,12)},k,d.slice(12));}).then(function(b){return new TextDecoder().decode(b);});}
  function run(code){return new Promise(function(ok,no){var u=URL.createObjectURL(new Blob([code],{type:"text/javascript"})),s=document.createElement("script");
    s.src=u;s.onload=function(){URL.revokeObjectURL(u);ok();};s.onerror=no;document.body.appendChild(s);});}
  function asset(raw,f){return fetch("/assets/"+f+".enc?v="+C.v).then(function(r){if(!r.ok)throw new Error(f);return r.text();}).then(function(t){return dec(raw,t.trim());});}
  function open(raw){
    return dec(raw,DATA).then(function(json){
      var P=JSON.parse(json); try{localStorage.setItem(K,toB64(raw));}catch(e){}
      document.title=P.title; document.body.innerHTML=P.body;
      return asset(raw,"data.js").then(run).then(function(){return asset(raw,"app.js");}).then(run);
    });
  }
  function form(msg){
    document.body.innerHTML='<main class="gate"><img src="/img/logo.png" alt="EVChargeking"><div class="eyebrow">'+T.h+'</div><p>'+T.p+'</p>'+
      '<form><label for="gp">'+T.l+'</label><input id="gp" type="password" autocomplete="current-password" required autofocus><button class="btn" type="submit">'+T.b+'</button>'+
      '<p class="err" role="alert">'+(msg||"")+'</p></form></main>';
    document.querySelector(".gate form").onsubmit=function(e){e.preventDefault();var v=document.getElementById("gp").value;
      derive(v).then(open).catch(function(){form(T.e);});};
  }
  if(!sub){document.body.textContent="This preview needs a current browser and a secure (https) connection.";return;}
  var saved=null; try{saved=localStorage.getItem(K);}catch(e){}
  if(saved)open(b64(saved)).catch(function(){try{localStorage.removeItem(K);}catch(e){} form();}); else form();
})();
