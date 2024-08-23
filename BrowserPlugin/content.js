function getFullPageContent() {
  return new Promise((resolve) => {
    // Wait for any remaining dynamic content to load
    setTimeout(() => {
      let content = document.documentElement.outerHTML;
      // Attempt to get content from iframes
      const iframes = document.getElementsByTagName('iframe');
      for (let i = 0; i < iframes.length; i++) {
        try {
          content += iframes[i].contentDocument.documentElement.outerHTML;
        } catch (e) {
          console.warn('Could not access iframe content:', e);
        }
      }
      resolve(content);
    }, 1000);  // Adjust this delay as needed
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getPageContent") {
    getFullPageContent().then(content => {
      sendResponse({content: content});
    });
    return true;  // Indicates we want to send a response asynchronously
  }
});