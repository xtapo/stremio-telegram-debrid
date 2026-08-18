function Mt(i,l){return i>>>=0,l&=31,l===0?i>>>0:(i<<l|i>>>32-l)>>>0}
function ue(i){return i>>>=0,i^=i>>>16,i=Math.imul(i,2246822507)>>>0,i^=i>>>13,i=Math.imul(i,3266489909)>>>0,(i^i>>>16)>>>0}
function tr(i,l){const d=new Array(61);let u=2166136261;for(let v=0;v<i.length;v++)u=Math.imul(u^i.charCodeAt(v),16777619)>>>0;u=ue(u);let m=ue(u^ue(l>>>0^2654435769))>>>0;for(let v=0;v<8;v++){const N=m%61;m=Mt(m+2654435769>>>0,7+(7&v)),d[N]=(m^ue(m))>>>0,m=ue(m+N>>>0)}return{S:d,acc:ue((2779096485^m)>>>0)>>>0}}
function sr(i,l){const d=i.S,u=i.acc,m=u%61,v=0-+(m in d),C=((d[m]??0)>>>0^Math.imul(2654435769,l+1)>>>0)>>>0,x=((u^C)>>>0|(u&C&v)>>>0)>>>0,b=(Mt(x+u>>>0,31&m)^Mt(u,31&Math.imul(m,7)))>>>0,j=ue(b+2654435769>>>0);return d[m]=j>>>0,i.acc=j,j>>>0}
function rr(i,l,d){const u=i.replace(/-/g,"+").replace(/_/g,"/").padEnd(4*Math.ceil(i.length/4),"="),m=atob(u),v=new Uint8Array(m.length);for(let b=0;b<m.length;b++)v[b]=m.charCodeAt(b);const N=tr(l,d);let C=0,x=0;for(;x<v.length;){const b=sr(N,C++);v[x++]^=b&255,x<v.length&&(v[x++]^=b>>>8&255),x<v.length&&(v[x++]^=b>>>16&255),x<v.length&&(v[x++]^=b>>>24&255)}return new TextDecoder().decode(v.subarray(4))}

async function test() {
    const tmdbId = 550;
    const headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://ernax.pro/',
        'Origin': 'https://ernax.pro'
    };
    
    console.log("Fetching seed...");
    const seedRes = await fetch(`https://api.speedracelight.com/seed?mediaId=${tmdbId}`, { headers });
    const { seed } = await seedRes.json();
    console.log("Seed:", seed);
    
    const params = new URLSearchParams({
        title: "Fight Club",
        mediaType: "movie",
        year: "1999",
        episodeId: "1",
        seasonId: "1",
        tmdbId: String(tmdbId),
        imdbId: "tt0137523",
        enc: "2",
        seed: seed
    });
    
    console.log("Fetching sources...");
    const srcRes = await fetch(`https://api.speedracelight.com/cdn/sources-with-title?${params}`, { headers });
    const text = await srcRes.text();
    console.log("Encrypted len:", text.length);
    
    const decrypted = rr(text, seed, tmdbId);
    console.log("Decrypted result:", decrypted);
}

test().catch(console.error);
