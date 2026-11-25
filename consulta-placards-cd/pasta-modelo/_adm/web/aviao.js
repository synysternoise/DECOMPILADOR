/* Perfil lateral de jato regional da família E1, em traço fino. Desenho próprio, sem marcas. */
(function(){
const s=document.getElementById('svg');
let jan='';for(let i=0;i<38;i++){const x=300+i*14.2;if(x>520&&x<566)continue;jan+=`<rect x="${x.toFixed(1)}" y="179" width="6.4" height="10" rx="3.2"/>`;}
s.innerHTML=`<defs>
 <linearGradient id="fus" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c9d1d9" stop-opacity=".10"/><stop offset=".55" stop-color="#c9d1d9" stop-opacity=".03"/><stop offset="1" stop-color="#c9d1d9" stop-opacity=".08"/></linearGradient>
 <linearGradient id="met" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c9d1d9" stop-opacity=".16"/><stop offset="1" stop-color="#c9d1d9" stop-opacity=".04"/></linearGradient>
</defs>
<g fill="none" stroke="#c9d1d9" stroke-linejoin="round" stroke-linecap="round">
 <path d="M902 158 C930 140 960 92 1004 20 L1056 20 C1062 60 1072 120 1084 176" fill="url(#met)" stroke-opacity=".55" stroke-width="1.2"/>
 <path d="M850 158 C880 157 892 156 902 158" stroke-opacity=".45" stroke-width="1.1"/>
 <path d="M1012 186 L1046 180 L1104 166 L1096 175 L1040 191 Z" fill="url(#met)" stroke-opacity=".5" stroke-width="1.1"/>
 <path d="M100 206 C100 186 136 166 196 160 C222 158 248 158 272 158 L900 158 C978 160 1056 172 1102 182 L1104 190 C1060 206 980 232 900 238 L820 241 L190 241 C130 237 100 224 100 206 Z" fill="url(#fus)" stroke-opacity=".75" stroke-width="1.3"/>
 <path d="M174 172 L204 164 L238 162 L238 171 L206 174 L180 178 Z" stroke-opacity=".6" stroke-width="1.1" fill="rgba(201,209,217,.08)"/>
 <g stroke-opacity=".38" stroke-width="1">${jan}</g>
 <rect x="262" y="166" width="24" height="56" rx="5" stroke-opacity=".42" stroke-width="1"/>
 <rect x="532" y="176" width="12" height="20" rx="3" stroke-opacity=".38"/><rect x="550" y="176" width="12" height="20" rx="3" stroke-opacity=".38"/>
 <rect x="852" y="166" width="22" height="52" rx="5" stroke-opacity=".42" stroke-width="1"/>
 <path d="M430 241 C470 254 600 255 660 241" stroke-opacity=".45" stroke-width="1.1"/>
 <path d="M468 230 L616 234 L694 214 L664 211 Z" fill="url(#met)" stroke-opacity=".6" stroke-width="1.2"/>
 <path d="M664 211 L694 214 L706 184 L697 183 Z" fill="url(#met)" stroke-opacity=".6" stroke-width="1.1"/>
 <path d="M478 246 L536 236 L540 248 L486 252 Z" stroke-opacity=".5" stroke-width="1.1" fill="rgba(201,209,217,.05)"/>
 <path d="M414 246 C414 238 420 234 432 234 L506 236 C520 238 530 246 532 258 C530 270 520 278 506 280 L432 282 C420 282 414 278 414 270 Z" fill="url(#met)" stroke-opacity=".7" stroke-width="1.2"/>
 <ellipse cx="416" cy="258" rx="5" ry="22" stroke-opacity=".55" stroke-width="1.1"/>
 <path d="M532 252 L548 258 L532 264" stroke-opacity=".45" stroke-width="1"/>
 <path d="M1102 182 L1112 185 L1104 190" stroke-opacity=".5" stroke-width="1"/>
 <line x1="120" y1="292" x2="1120" y2="292" stroke-opacity=".10" stroke-dasharray="2 8"/>
</g>
<path id="brilho" d="M300 184 L842 184" stroke="#d81e3a" stroke-width="2" stroke-linecap="round" fill="none"/>`;

})();
