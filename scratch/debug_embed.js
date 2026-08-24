async function debugEmbed() {
    const embedUrl = 'https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6';
    try {
        const res = await fetch(embedUrl, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://phim.nguonc.com/'
            }
        });
        console.log("Embed status:", res.status);
        const html = await res.text();
        console.log("HTML length:", html.length);
        
        // Match scripts
        const scripts = [...html.matchAll(/<script[^>]*src="([^"]+)"/gi)].map(m => m[1]);
        console.log("Script tags:", scripts);

        // Check if player.js exists
        for (const s of scripts) {
            const full = s.startsWith('http') ? s : new URL(s, embedUrl).href;
            console.log("Fetching script:", full);
            const sRes = await fetch(full, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'Referer': embedUrl
                }
            });
            console.log("Script status:", sRes.status, "Length:", (await sRes.text()).length);
        }
    } catch (e) {
        console.error("Debug error:", e);
    }
}
debugEmbed();
