async function getPlayerJs() {
    const embedUrl = 'https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6';
    const playerJsUrl = 'https://embed18.streamc.xyz/player.js?ver=1.8';
    const res = await fetch(playerJsUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': embedUrl
        }
    });
    console.log("Player.js status:", res.status);
    const code = await res.text();
    console.log("Player.js length:", code.length);
    const fs = require('fs');
    fs.writeFileSync('scratch/player_streamc.js', code);
    console.log("Saved to scratch/player_streamc.js");
}
getPlayerJs();
