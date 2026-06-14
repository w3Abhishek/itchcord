document.addEventListener('DOMContentLoaded', async () => {
    const primaryBtn = document.getElementById('primary-download');
    const primaryText = document.getElementById('download-text');
    const dlWindows = document.getElementById('dl-windows');
    const dlMacos = document.getElementById('dl-macos');
    const dlLinux = document.getElementById('dl-linux');

    // GitHub Repo info
    const owner = 'w3Abhishek';
    const repo = 'itchcord';
    const apiUrl = `https://api.github.com/repos/${owner}/${repo}/releases/latest`;
    const fallbackUrl = `https://github.com/${owner}/${repo}/releases/latest`;

    // Detect OS
    let userOS = "Unknown";
    const platform = window.navigator.platform.toLowerCase();
    const userAgent = window.navigator.userAgent.toLowerCase();

    if (platform.includes('win') || userAgent.includes('windows')) {
        userOS = "Windows";
    } else if (platform.includes('mac') || userAgent.includes('mac')) {
        userOS = "macOS";
    } else if (platform.includes('linux') || userAgent.includes('linux')) {
        userOS = "Linux";
    }

    // Update initial button text
    if (userOS !== "Unknown") {
        primaryText.textContent = `Download for ${userOS}`;
    } else {
        primaryText.textContent = `View Latest Release`;
        primaryBtn.href = fallbackUrl;
    }

    try {
        const response = await fetch(apiUrl);
        if (!response.ok) throw new Error('API Error');
        const release = await response.json();

        let winAsset = fallbackUrl;
        let macAsset = fallbackUrl;
        let linAsset = fallbackUrl;

        // Try to parse assets from the GitHub Release JSON
        release.assets.forEach(asset => {
            const name = asset.name.toLowerCase();
            if (name.includes('windows') || name.endsWith('.exe')) winAsset = asset.browser_download_url;
            else if (name.includes('macos') || name.includes('darwin')) macAsset = asset.browser_download_url;
            else if (name.includes('linux') || name.includes('ubuntu')) linAsset = asset.browser_download_url;
        });

        dlWindows.href = winAsset;
        dlMacos.href = macAsset;
        dlLinux.href = linAsset;

        // Set primary button link
        if (userOS === "Windows") primaryBtn.href = winAsset;
        else if (userOS === "macOS") primaryBtn.href = macAsset;
        else if (userOS === "Linux") primaryBtn.href = linAsset;

    } catch (err) {
        console.error("Failed to fetch GitHub release:", err);
        // Defaults to fallback URL set in HTML
        dlWindows.href = fallbackUrl;
        dlMacos.href = fallbackUrl;
        dlLinux.href = fallbackUrl;
    }
});
