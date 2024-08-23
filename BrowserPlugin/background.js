// background.js

let visitStartTime = {};
const MINIMUM_VISIT_TIME = 20 * 60 * 1000; // 20 minutes in milliseconds

// Function to generate hash
function generateHash(content) {
  const encoder = new TextEncoder();
  const data = encoder.encode(content);
  return crypto.subtle.digest('SHA-256', data).then(hashBuffer => {
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  });
}

// Function to get cleaned content
function getCleanedContent(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { action: "getPageContent" }, function(response) {
      if (chrome.runtime.lastError) {
        console.error('Error:', chrome.runtime.lastError);
        resolve('');
      } else if (response && response.content) {
        resolve(response.content);
      } else {
        console.warn('No content received from tab');
        resolve('');
      }
    });
  });
}

// Function to get cookies for a given URL
function getCookiesForUrl(url) {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ url: url }, (cookies) => {
      resolve(cookies);
    });
  });
}

// Function to check if a URL is bookmarked
function isBookmarked(url) {
  return new Promise((resolve) => {
    chrome.bookmarks.search({ url: url }, (results) => {
      resolve(results.length > 0);
    });
  });
}

// Function to get geolocation
function getGeolocation() {
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude
      }),
      () => resolve(null)
    );
  });
}

// Function to get top sites
function getTopSites() {
  return new Promise((resolve) => {
    chrome.topSites.get((sites) => {
      resolve(sites.slice(0, 5)); // Get top 5 sites
    });
  });
}

// Function to get idle state
function getIdleState() {
  return new Promise((resolve) => {
    chrome.idle.queryState(30, (state) => { // 30 seconds threshold
      resolve(state);
    });
  });
}

// Function to check if URL should be ignored
function shouldIgnoreUrl(url) {
  // Add your logic here to determine if a URL should be ignored
  // For example, you might want to ignore certain domains or URL patterns
  return false;
}

// Listen for tab updates
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && !shouldIgnoreUrl(tab.url)) {
    visitStartTime[tabId] = Date.now();
    // Wait a bit to allow dynamic content to load
    setTimeout(() => {
      recordVisit(tab);
    }, 2000);  // Adjust this delay as needed
  }
});

// Listen for tab removal
chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
  delete visitStartTime[tabId];
});

// Listen for tab activation changes
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const previousTab = await new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      resolve(tabs[0]);
    });
  });

  if (previousTab && visitStartTime[previousTab.id]) {
    const visitDuration = Date.now() - visitStartTime[previousTab.id];
    if (visitDuration >= MINIMUM_VISIT_TIME) {
      const content = await getCleanedContent(previousTab.id);
      recordVisit(previousTab, content);
    }
    delete visitStartTime[previousTab.id];
  }

  visitStartTime[activeInfo.tabId] = Date.now();
});

// Periodically check for long visits on the current tab
setInterval(async () => {
  const currentTab = await new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      resolve(tabs[0]);
    });
  });

  if (currentTab && visitStartTime[currentTab.id]) {
    const visitDuration = Date.now() - visitStartTime[currentTab.id];
    if (visitDuration >= MINIMUM_VISIT_TIME) {
      const content = await getCleanedContent(currentTab.id);
      recordVisit(currentTab, content);
      visitStartTime[currentTab.id] = Date.now(); // Reset the timer
    }
  }
}, MINIMUM_VISIT_TIME);

// Function to record visit
async function recordVisit(tab, content = null) {
  if (shouldIgnoreUrl(tab.url)) {
    console.log(`Ignoring visit to ${tab.url}`);
    return;
  }

  const timestamp = new Date().toISOString();
  const url = tab.url;

  if (!content) {
    console.log(`Attempting to capture content for ${url}`);
    content = await getCleanedContent(tab.id);
    if (!content) {
      console.warn(`Failed to capture content for ${url}`);
      return; // Don't proceed if content is empty
    } else {
      console.log(`Successfully captured ${content.length} characters for ${url}`);
    }
  }

  const contentHash = await generateHash(content);

  // Collect additional metadata
  const [
    cookies,
    _isBookmarked,
    geolocation,
    topSites,
    idleState
  ] = await Promise.all([
    getCookiesForUrl(url),
    isBookmarked(url),
    getGeolocation(),
    getTopSites(),
    getIdleState()
  ]);

  // Get browsing history for the last 24 hours
  const yesterday = new Date(Date.now() - 86400000).getTime();
  const history = await new Promise((resolve) => {
    chrome.history.search({ text: '', startTime: yesterday, maxResults: 100 }, (results) => {
      resolve(results);
    });
  });

  const visitData = {
    timestamp: timestamp,
    url: url,
    title: tab.title,
    content: content,
    contentHash: contentHash,
    version: 0, // The server will handle versioning
    metadata: {
      cookies: cookies,
      isBookmarked: _isBookmarked,
      geolocation: geolocation,
      topSites: topSites,
      idleState: idleState,
      recentHistory: history
    }
  };

  // Send data to API
  fetch('http://127.0.0.1:8088/visit', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(visitData),
  })
  .then(response => {
    if (!response.ok) {
      return response.json().then(err => {
        throw new Error(`HTTP error! status: ${response.status}, message: ${JSON.stringify(err)}`);
      });
    }
    return response.json();
  })
  .then(data => console.log('Success:', data))
  .catch((error) => console.error('Error:', error));
}