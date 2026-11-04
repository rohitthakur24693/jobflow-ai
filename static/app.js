// ============================================================================
// JobFlow AI — Intelligent Job Search & Application Assistant (app.js)
// ============================================================================

// Global Application State
let appState = {
  user: null,
  currentResume: null,
  jobs: [],
  selectedJobId: null,
  resultsView: 'split',
  mainTab: 'jobs',
  gmail: {
    connected: false,
    email: null,
    first_name: '',
    last_name: '',
    full_name: '',
    auth_mode: null
  },
  linkedin: {
    authenticated: false,
    profile_path: null,
    server: null
  },
  filters: {
    locations: [],
    work_arrangements: [],
    experience_levels: [],
    industries: [],
    companies: [],
    sources: ['linkedin', 'indeed', 'remote_boards', 'curated'],
    custom_locations: [],
    custom_industries: []
  },
  tracker: {
    items: [],
    stats: {},
    activeStatusFilter: 'All'
  }
};

// ============================================================================
// AUTHENTICATION & MULTI-TENANT ISOLATION HELPERS
// ============================================================================

function getAuthToken() {
  return localStorage.getItem("jobflow_token") || "";
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem("jobflow_token", token);
  } else {
    localStorage.removeItem("jobflow_token");
  }
}

// Global authenticated fetch wrapper
async function authFetch(url, options = {}) {
  const token = getAuthToken();
  const headers = options.headers ? { ...options.headers } : {};
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const fetchOptions = {
    ...options,
    headers,
    credentials: "include"
  };

  const res = await fetch(url, fetchOptions);

  if (res.status === 401 && token) {
    setAuthToken(null);
    updateAuthUI(null);
  }
  return res;
}

let currentAuthMode = 'login';

function openAuthModal(mode = 'login') {
  const modal = document.getElementById("authModal");
  if (modal) modal.classList.remove("hidden");
  switchAuthMode(mode);
}

function closeAuthModal() {
  const modal = document.getElementById("authModal");
  if (modal) modal.classList.add("hidden");
  const errBox = document.getElementById("authErrorMessage");
  if (errBox) {
    errBox.classList.add("hidden");
    errBox.innerText = "";
  }
}

function switchAuthMode(mode) {
  currentAuthMode = mode;
  const title = document.getElementById("authModalTitle");
  const tabLogin = document.getElementById("authTabBtnLogin");
  const tabRegister = document.getElementById("authTabBtnRegister");
  const regFields = document.getElementById("authRegisterFields");
  const submitBtn = document.getElementById("authSubmitBtn");
  const toggleHint = document.getElementById("authToggleHint");
  const toggleBtn = document.getElementById("authToggleBtn");
  const errBox = document.getElementById("authErrorMessage");

  if (errBox) {
    errBox.classList.add("hidden");
    errBox.innerText = "";
  }

  if (mode === 'login') {
    if (title) title.innerText = "Sign In to JobFlow AI";
    if (tabLogin) tabLogin.className = "flex-1 py-2 rounded-lg bg-emerald-600 text-white transition-all text-center font-semibold shadow-sm";
    if (tabRegister) tabRegister.className = "flex-1 py-2 rounded-lg text-slate-400 hover:text-white transition-all text-center";
    if (regFields) regFields.classList.add("hidden");
    if (submitBtn) submitBtn.innerText = "Sign In";
    if (toggleHint) toggleHint.innerText = "Don't have an account?";
    if (toggleBtn) toggleBtn.innerText = "Create one now";
  } else {
    if (title) title.innerText = "Create Your Private Workspace";
    if (tabRegister) tabRegister.className = "flex-1 py-2 rounded-lg bg-emerald-600 text-white transition-all text-center font-semibold shadow-sm";
    if (tabLogin) tabLogin.className = "flex-1 py-2 rounded-lg text-slate-400 hover:text-white transition-all text-center";
    if (regFields) regFields.classList.remove("hidden");
    if (submitBtn) submitBtn.innerText = "Create Account";
    if (toggleHint) toggleHint.innerText = "Already have an account?";
    if (toggleBtn) toggleBtn.innerText = "Sign in here";
  }
  lucide.createIcons();
}

function toggleAuthMode() {
  switchAuthMode(currentAuthMode === 'login' ? 'register' : 'login');
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const errBox = document.getElementById("authErrorMessage");
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;
  const firstName = document.getElementById("authFirstName") ? document.getElementById("authFirstName").value.trim() : "";
  const lastName = document.getElementById("authLastName") ? document.getElementById("authLastName").value.trim() : "";
  const submitBtn = document.getElementById("authSubmitBtn");

  if (errBox) errBox.classList.add("hidden");
  if (!email || !password) {
    if (errBox) {
      errBox.innerText = "Email and password are required.";
      errBox.classList.remove("hidden");
    }
    return;
  }

  const origBtnText = submitBtn.innerText;
  submitBtn.innerText = "Authenticating...";
  submitBtn.disabled = true;

  try {
    const endpoint = currentAuthMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    const payload = { email, password };
    if (currentAuthMode === 'register') {
      payload.first_name = firstName;
      payload.last_name = lastName;
    }

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      if (errBox) {
        errBox.innerText = data.detail || data.message || "Authentication failed. Please verify credentials.";
        errBox.classList.remove("hidden");
      }
      submitBtn.innerText = origBtnText;
      submitBtn.disabled = false;
      return;
    }

    setAuthToken(data.access_token || data.token);
    closeAuthModal();
    document.getElementById("authPassword").value = "";

    showToast(`Welcome ${data.user.full_name || data.user.email}! Workspace activated.`);
    
    await checkSystemStatus();
    await loadUserProfile();
    await loadTrackerData();
    await loadSchedulerData();

  } catch (err) {
    if (errBox) {
      errBox.innerText = "Connection error: " + err.message;
      errBox.classList.remove("hidden");
    }
  } finally {
    submitBtn.innerText = origBtnText;
    submitBtn.disabled = false;
  }
}

async function handleLogout() {
  try {
    await authFetch("/api/auth/logout", { method: "POST" });
  } catch (e) {
    console.error("Logout request error:", e);
  }

  setAuthToken(null);
  appState.user = null;
  appState.currentResume = null;
  appState.jobs = [];
  appState.selectedJobId = null;
  appState.gmail = {
    connected: false,
    email: null,
    first_name: '',
    last_name: '',
    full_name: '',
    auth_mode: null
  };
  appState.tracker = {
    items: [],
    stats: {},
    activeStatusFilter: 'All'
  };

  updateAuthUI(null);
  resetResumeUI();
  
  renderTrackerTable();
  renderTrackerStats({});
  const navTrackerCount = document.getElementById("navTrackerCount");
  if (navTrackerCount) navTrackerCount.innerText = "0";

  const cardsContainer = document.getElementById("jobCardsList");
  if (cardsContainer) cardsContainer.innerHTML = `
    <div class="py-16 text-center text-slate-500">
      <i data-lucide="shield" class="w-10 h-10 mx-auto mb-2 text-slate-600"></i>
      <p class="text-sm font-semibold text-slate-400">Signed Out</p>
      <p class="text-xs text-slate-500 mt-1">Please sign in to access your personal workspace and jobs.</p>
    </div>
  `;
  const detailEmpty = document.getElementById("jobDetailEmpty");
  const detailContent = document.getElementById("jobDetailContent");
  if (detailEmpty) detailEmpty.classList.remove("hidden");
  if (detailContent) detailContent.classList.add("hidden");

  const pFirst = document.getElementById("profileFirstName");
  const pLast = document.getElementById("profileLastName");
  if (pFirst) pFirst.value = "";
  if (pLast) pLast.value = "";

  renderSchedulerUI({
    enabled: false,
    frequency: "every_6_hours",
    keywords: "",
    locations: [],
    auto_create_draft: false,
    next_run_time: null,
    last_run_status: "Please sign in to configure autonomous scheduler"
  });

  showToast("Logged out safely. Workspace is clean.");
  lucide.createIcons();
}

function updateAuthUI(user) {
  const btnSignIn = document.getElementById("navBtnSignIn");
  const userBadge = document.getElementById("navUserBadge");
  const userEmail = document.getElementById("navUserEmail");
  const userInitial = document.getElementById("navUserInitial");

  if (user && user.email) {
    if (btnSignIn) btnSignIn.classList.add("hidden");
    if (userBadge) userBadge.classList.remove("hidden");
    if (userEmail) userEmail.innerText = user.email;
    const nameToUse = user.full_name || user.email;
    if (userInitial) userInitial.innerText = nameToUse.charAt(0).toUpperCase();
  } else {
    if (btnSignIn) btnSignIn.classList.remove("hidden");
    if (userBadge) userBadge.classList.add("hidden");
  }
  lucide.createIcons();
}

function resetResumeUI() {
  appState.currentResume = null;
  const bannerFilename = document.getElementById("bannerResumeFilename");
  const bannerCandidate = document.getElementById("bannerCandidateName");
  const bannerDownload = document.getElementById("bannerDownloadBtn");
  const navDot = document.getElementById("navResumeDot");

  if (bannerFilename) bannerFilename.innerText = "No resume uploaded yet";
  if (bannerCandidate) bannerCandidate.innerText = "(Upload to match jobs & attach original filename)";
  if (bannerDownload) bannerDownload.classList.add("hidden");
  if (navDot) navDot.className = "w-2 h-2 rounded-full bg-slate-600";

  const detailAttach = document.getElementById("detailAttachmentFilename");
  if (detailAttach) detailAttach.innerText = "None attached";

  const emptyBox = document.getElementById("resumeAnalysisEmpty");
  const contentBox = document.getElementById("resumeAnalysisContent");
  const statusBadge = document.getElementById("parsedResumeStatusBadge");

  if (emptyBox) emptyBox.classList.remove("hidden");
  if (contentBox) contentBox.classList.add("hidden");
  if (statusBadge) {
    statusBadge.innerText = "No resume";
    statusBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-mono";
  }
}

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  setupDragAndDrop();
  checkSystemStatus();
  loadUserProfile();
  loadTrackerData();
  loadSchedulerData();
  updateActiveFilterTags();
});

// ============================================================================
// NAVIGATION & TABS
// ============================================================================

function switchMainTab(tab) {
  appState.mainTab = tab;
  
  const viewJobs = document.getElementById("viewTabJobs");
  const viewTracker = document.getElementById("viewTabTracker");
  const viewScheduler = document.getElementById("viewTabScheduler");
  const viewResume = document.getElementById("viewTabResume");

  const navJobs = document.getElementById("navTabJobs");
  const navTracker = document.getElementById("navTabTracker");
  const navScheduler = document.getElementById("navTabScheduler");
  const navResume = document.getElementById("navTabResume");

  [viewJobs, viewTracker, viewScheduler, viewResume].forEach(el => {
    if (el) el.classList.add("hidden");
  });
  [navJobs, navTracker, navScheduler, navResume].forEach(el => {
    if (el) {
      el.classList.remove("bg-emerald-500/10", "text-emerald-400", "border", "border-emerald-500/20");
      el.classList.add("text-slate-400");
    }
  });

  if (tab === 'jobs') {
    if (viewJobs) viewJobs.classList.remove("hidden");
    if (navJobs) {
      navJobs.classList.add("bg-emerald-500/10", "text-emerald-400", "border", "border-emerald-500/20");
      navJobs.classList.remove("text-slate-400");
    }
  } else if (tab === 'tracker') {
    if (viewTracker) viewTracker.classList.remove("hidden");
    if (navTracker) {
      navTracker.classList.add("bg-emerald-500/10", "text-emerald-400", "border", "border-emerald-500/20");
      navTracker.classList.remove("text-slate-400");
    }
    loadTrackerData();
  } else if (tab === 'scheduler') {
    if (viewScheduler) viewScheduler.classList.remove("hidden");
    if (navScheduler) {
      navScheduler.classList.add("bg-emerald-500/10", "text-emerald-400", "border", "border-emerald-500/20");
      navScheduler.classList.remove("text-slate-400");
    }
    loadSchedulerData();
  } else if (tab === 'resume') {
    if (viewResume) viewResume.classList.remove("hidden");
    if (navResume) {
      navResume.classList.add("bg-emerald-500/10", "text-emerald-400", "border", "border-emerald-500/20");
      navResume.classList.remove("text-slate-400");
    }
  }

  lucide.createIcons();
}

function switchResultsView(view) {
  appState.resultsView = view;
  const splitCont = document.getElementById("splitViewContainer");
  const gridCont = document.getElementById("gridViewContainer");
  const tableCont = document.getElementById("tableViewContainer");

  const btnSplit = document.getElementById("viewBtnSplit");
  const btnGrid = document.getElementById("viewBtnGrid");
  const btnTable = document.getElementById("viewBtnTable");

  [splitCont, gridCont, tableCont].forEach(c => { if (c) c.classList.add("hidden"); });
  [btnSplit, btnGrid, btnTable].forEach(b => {
    if (b) b.className = "px-2.5 py-1 rounded-md text-slate-400 hover:text-slate-200 flex items-center space-x-1.5 transition-all";
  });

  const activeBtnClass = "px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-400 font-semibold flex items-center space-x-1.5 transition-all";

  if (view === 'split') {
    if (splitCont) splitCont.classList.remove("hidden");
    if (btnSplit) btnSplit.className = activeBtnClass;
    renderJobCards();
  } else if (view === 'grid') {
    if (gridCont) gridCont.classList.remove("hidden");
    if (btnGrid) btnGrid.className = activeBtnClass;
    renderGridView();
  } else if (view === 'table') {
    if (tableCont) tableCont.classList.remove("hidden");
    if (btnTable) btnTable.className = activeBtnClass;
    renderTableView();
  }
  lucide.createIcons();
}

// ============================================================================
// SYSTEM & PROFILE STATUS
// ============================================================================

async function checkSystemStatus() {
  try {
    const res = await authFetch("/api/status");
    const data = await res.json();

    // User authentication status
    if (data.authenticated && data.user) {
      appState.user = data.user;
      updateAuthUI(data.user);
    } else {
      appState.user = null;
      updateAuthUI(null);
    }

    // Gmail status
    appState.gmail = data.gmail;
    const gmailDot = document.getElementById("gmailStatusDot");
    const gmailText = document.getElementById("gmailStatusText");
    const modalDisplay = document.getElementById("modalGmailStatusDisplay");
    const modalPill = document.getElementById("modalGmailStatusPill");
    const modalProfileName = document.getElementById("modalGmailProfileName");
    const connectedActions = document.getElementById("gmailConnectedActions");
    const notConnectedSection = document.getElementById("gmailNotConnectedSection");

    if (data.gmail && data.gmail.connected) {
      gmailDot.className = "w-2 h-2 rounded-full bg-emerald-400";
      const displayName = data.gmail.full_name || data.gmail.email;
      gmailText.innerText = `Gmail: ${displayName}`;
      if (modalDisplay) modalDisplay.innerText = `Connected as ${data.gmail.email}`;
      if (modalProfileName) modalProfileName.innerText = `Profile: ${data.gmail.full_name || 'Verified'}`;
      if (modalPill) {
        modalPill.innerText = "Connected";
        modalPill.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
      }
      if (connectedActions) connectedActions.classList.remove("hidden");
      if (notConnectedSection) notConnectedSection.classList.add("hidden");
    } else {
      gmailDot.className = "w-2 h-2 rounded-full bg-amber-400";
      gmailText.innerText = "Gmail: Connect";
      if (modalDisplay) modalDisplay.innerText = "Not Connected";
      if (modalProfileName) modalProfileName.innerText = "";
      if (modalPill) {
        modalPill.innerText = "Not Connected";
        modalPill.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20";
      }
      if (connectedActions) connectedActions.classList.add("hidden");
      if (notConnectedSection) notConnectedSection.classList.remove("hidden");
    }

    // LinkedIn MCP status
    appState.linkedin = data.linkedin;
    const linkedinDot = document.getElementById("linkedinStatusDot");
    const linkedinText = document.getElementById("linkedinStatusText");
    const modalLinkedInStatus = document.getElementById("modalLinkedInStatusDisplay");

    if (data.linkedin && data.linkedin.authenticated) {
      if (linkedinDot) linkedinDot.className = "w-2 h-2 rounded-full bg-emerald-400";
      if (linkedinText) linkedinText.innerText = "LinkedIn: Connected";
      if (modalLinkedInStatus) {
        modalLinkedInStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span>Authenticated & Connected</span>`;
      }
    } else {
      if (linkedinDot) linkedinDot.className = "w-2 h-2 rounded-full bg-amber-400";
      if (linkedinText) linkedinText.innerText = "LinkedIn: Sync Needed";
      if (modalLinkedInStatus) {
        modalLinkedInStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400"></span><span>Needs Sync / Reconnect</span>`;
      }
    }

    // Tracker stats badge in nav
    if (data.tracker_stats) {
      document.getElementById("navTrackerCount").innerText = data.tracker_stats.Total || 0;
    }

    // If session has resume, load it, otherwise reset resume UI
    if (data.has_resume && data.resume) {
      appState.currentResume = data.resume;
      updateResumeUI({
        original_filename: data.resume.original_filename || data.resume.file_name,
        file_name: data.resume.file_name,
        name: data.resume.candidate_name,
        email: data.resume.email,
        years_of_experience: data.resume.years_of_experience,
        skills: []
      });
    } else {
      resetResumeUI();
    }

  } catch (err) {
    console.error("Error checking system status:", err);
  }
}

async function loadUserProfile() {
  try {
    const res = await authFetch("/api/user/profile");
    if (!res.ok) {
      document.getElementById("profileFirstName").value = '';
      document.getElementById("profileLastName").value = '';
      document.getElementById("detailSignaturePreview").innerText = '';
      return;
    }
    const data = await res.json();
    if (data.first_name || data.last_name) {
      document.getElementById("profileFirstName").value = data.first_name || '';
      document.getElementById("profileLastName").value = data.last_name || '';
      const fullName = data.full_name || `${data.first_name} ${data.last_name}`.trim();
      if (fullName) {
        document.getElementById("detailSignaturePreview").innerText = fullName;
      }
    }
  } catch (err) {
    console.error("Error loading user profile:", err);
  }
}

async function saveUserProfileName() {
  const firstName = document.getElementById("profileFirstName").value.trim();
  const lastName = document.getElementById("profileLastName").value.trim();

  if (!firstName) {
    showToast("Please enter at least a first name", true);
    return;
  }

  try {
    const res = await authFetch("/api/user/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ first_name: firstName, last_name: lastName })
    });
    if (res.status === 401) {
      showToast("Please sign in or create an account to save your profile", true);
      openAuthModal('login');
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Email signature name saved: " + data.full_name);
      document.getElementById("detailSignaturePreview").innerText = data.full_name;
      // Refresh current job draft body signature if job selected
      if (appState.selectedJobId) {
        const job = appState.jobs.find(j => j.id === appState.selectedJobId);
        if (job) selectJob(job.id);
      }
      checkSystemStatus();
    }
  } catch (err) {
    showToast("Failed to save profile name", true);
  }
}

async function syncProfileFromGmail() {
  await checkSystemStatus();
  await loadUserProfile();
  showToast("Profile name synced with Gmail");
}

// ============================================================================
// RESUME UPLOAD & FILENAME PRESERVATION
// ============================================================================

function setupDragAndDrop() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("resumeFileInput");

  if (!dropZone || !fileInput) return;

  dropZone.addEventListener("click", () => fileInput.click());

  ["dragenter", "dragover"].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.add("border-emerald-500", "bg-emerald-950/20");
    });
  });

  ["dragleave", "drop"].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.remove("border-emerald-500", "bg-emerald-950/20");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) uploadResumeFile(files[0]);
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) uploadResumeFile(e.target.files[0]);
  });
}

async function uploadResumeFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  showToast(`Uploading ${file.name}...`);

  try {
    const res = await authFetch("/api/resume/upload", {
      method: "POST",
      body: formData
    });

    if (res.status === 401) {
      showToast("Please sign in or create an account to upload your resume.", true);
      openAuthModal('login');
      return;
    }

    const data = await res.json();

    if (data.success) {
      showToast(`Resume uploaded: ${data.original_filename}`);
      appState.currentResume = data.resume;
      updateResumeUI(data.resume);
      // Auto switch back to jobs tab to search
      switchMainTab('jobs');
    } else {
      showToast(data.detail || "Upload failed", true);
    }
  } catch (err) {
    showToast("Error uploading file: " + err.message, true);
  }
}

function updateResumeUI(resume) {
  if (!resume) return;

  const originalFilename = resume.original_filename || resume.file_name || "Resume.pdf";

  // 1. Top banner notice
  const bannerFilename = document.getElementById("bannerResumeFilename");
  const bannerCandidate = document.getElementById("bannerCandidateName");
  const bannerDownload = document.getElementById("bannerDownloadBtn");
  const navDot = document.getElementById("navResumeDot");

  if (bannerFilename) bannerFilename.innerText = originalFilename;
  if (bannerCandidate) bannerCandidate.innerText = `(${resume.name || 'Candidate'})`;
  if (bannerDownload) bannerDownload.classList.remove("hidden");
  if (navDot) navDot.className = "w-2 h-2 rounded-full bg-emerald-400";

  // 2. Right pane attachment badge
  const detailAttach = document.getElementById("detailAttachmentFilename");
  if (detailAttach) detailAttach.innerText = originalFilename;

  // 3. Tab 3 Parsed Facts
  const emptyBox = document.getElementById("resumeAnalysisEmpty");
  const contentBox = document.getElementById("resumeAnalysisContent");
  const statusBadge = document.getElementById("parsedResumeStatusBadge");

  if (emptyBox) emptyBox.classList.add("hidden");
  if (contentBox) contentBox.classList.remove("hidden");
  if (statusBadge) {
    statusBadge.innerText = originalFilename;
    statusBadge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono";
  }

  document.getElementById("factsCandidateName").innerText = resume.name || "Candidate";
  document.getElementById("factsCandidateContact").innerText = [resume.email, resume.phone].filter(Boolean).join(" • ") || "No contact info parsed";
  document.getElementById("factsYearsExp").innerText = `${resume.years_of_experience || 3} Years Experience`;

  // Render skills chips
  const skillsContainer = document.getElementById("factsSkillsChips");
  if (skillsContainer) {
    skillsContainer.innerHTML = "";
    const skills = resume.skills || [];
    document.getElementById("factsSkillsCount").innerText = `${skills.length} skills`;
    skills.forEach(s => {
      const chip = document.createElement("span");
      chip.className = "px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-[11px] border border-slate-700 font-medium";
      chip.innerText = s;
      skillsContainer.appendChild(chip);
    });
  }

  // Pre-fill profile name if empty
  if (resume.name && !document.getElementById("profileFirstName").value) {
    const parts = resume.name.split(" ");
    document.getElementById("profileFirstName").value = parts[0] || "";
    document.getElementById("profileLastName").value = parts.slice(1).join(" ") || "";
    document.getElementById("detailSignaturePreview").innerText = resume.name;
  }
}

async function downloadActiveResume() {
  try {
    const res = await authFetch("/api/resume/download");
    if (res.status === 401) {
      showToast("Please sign in to access your resume", true);
      openAuthModal("login");
      return;
    }
    if (!res.ok) {
      showToast("No resume found or unauthorized", true);
      return;
    }
    const blob = await res.blob();
    let filename = appState.currentResume?.original_filename || "Resume.pdf";
    const disposition = res.headers.get("content-disposition");
    if (disposition && disposition.indexOf("filename=") !== -1) {
      const match = disposition.match(/filename="?([^";]+)"?/);
      if (match && match[1]) filename = match[1];
    }
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    showToast("Error downloading resume: " + err.message, true);
  }
}

// ============================================================================
// MULTI-SELECT FILTER RIBBON LOGIC
// ============================================================================

function toggleFilterPill(btn, type, value) {
  btn.classList.toggle("active-pill");
  const isActive = btn.classList.contains("active-pill");

  if (type === 'location') {
    if (isActive) {
      if (!appState.filters.locations.includes(value)) appState.filters.locations.push(value);
    } else {
      appState.filters.locations = appState.filters.locations.filter(v => v !== value);
    }
  } else if (type === 'arrangement') {
    if (isActive) {
      if (!appState.filters.work_arrangements.includes(value)) appState.filters.work_arrangements.push(value);
    } else {
      appState.filters.work_arrangements = appState.filters.work_arrangements.filter(v => v !== value);
    }
  } else if (type === 'experience') {
    if (isActive) {
      if (!appState.filters.experience_levels.includes(value)) appState.filters.experience_levels.push(value);
    } else {
      appState.filters.experience_levels = appState.filters.experience_levels.filter(v => v !== value);
    }
  } else if (type === 'industry') {
    if (isActive) {
      if (!appState.filters.industries.includes(value)) appState.filters.industries.push(value);
    } else {
      appState.filters.industries = appState.filters.industries.filter(v => v !== value);
    }
  } else if (type === 'source') {
    if (!appState.filters.sources) appState.filters.sources = [];
    if (isActive) {
      if (!appState.filters.sources.includes(value)) appState.filters.sources.push(value);
    } else {
      appState.filters.sources = appState.filters.sources.filter(v => v !== value);
    }
  }

  updateActiveFilterTags();
}

function handleCustomLocationKey(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    addCustomLocation();
  }
}

function addCustomLocation() {
  const input = document.getElementById("customLocationInput");
  const val = input.value.trim();
  if (!val) return;

  if (!appState.filters.locations.includes(val)) {
    appState.filters.locations.push(val);
    appState.filters.custom_locations.push(val);
    
    // Add pill dynamically
    const container = document.getElementById("locationPillsContainer");
    const newBtn = document.createElement("button");
    newBtn.type = "button";
    newBtn.className = "filter-pill active-pill px-3 py-1 rounded-lg text-xs font-medium border transition-all";
    newBtn.innerText = val;
    newBtn.onclick = () => toggleFilterPill(newBtn, 'location', val);
    container.insertBefore(newBtn, input.parentElement);
  }
  input.value = "";
  updateActiveFilterTags();
}

function handleCustomIndustryKey(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    addCustomIndustry();
  }
}

function addCustomIndustry() {
  const input = document.getElementById("customIndustryInput");
  const val = input.value.trim();
  if (!val) return;

  if (!appState.filters.industries.includes(val)) {
    appState.filters.industries.push(val);
    appState.filters.custom_industries.push(val);
    
    // Add pill dynamically
    const container = document.getElementById("industryContainer");
    const newBtn = document.createElement("button");
    newBtn.type = "button";
    newBtn.className = "filter-pill active-pill px-3 py-1 rounded-lg text-xs font-medium border transition-all";
    newBtn.innerText = val;
    newBtn.onclick = () => toggleFilterPill(newBtn, 'industry', val);
    container.insertBefore(newBtn, input.parentElement);
  }
  input.value = "";
  updateActiveFilterTags();
}

function updateActiveFilterTags() {
  const container = document.getElementById("activeFilterTagsList");
  if (!container) return;
  container.innerHTML = "";

  const allSelected = [
    ...appState.filters.locations.map(v => ({ type: 'location', label: `📍 ${v}`, val: v })),
    ...appState.filters.work_arrangements.map(v => ({ type: 'arrangement', label: `💻 ${v}`, val: v })),
    ...appState.filters.experience_levels.map(v => ({ type: 'experience', label: `⭐ ${v}`, val: v })),
    ...appState.filters.industries.map(v => ({ type: 'industry', label: `🏢 ${v}`, val: v }))
  ];

  if (allSelected.length === 0) {
    container.innerHTML = `<span class="text-slate-500 italic">No filters active (searching all)</span>`;
    return;
  }

  allSelected.forEach(item => {
    const chip = document.createElement("span");
    chip.className = "inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 text-[11px]";
    chip.innerHTML = `<span>${item.label}</span><button type="button" class="text-slate-500 hover:text-rose-400 pl-1 font-bold">&times;</button>`;
    chip.querySelector("button").onclick = () => removeFilterTag(item.type, item.val);
    container.appendChild(chip);
  });
}

function removeFilterTag(type, val) {
  // Find matching pill button and toggle it off
  let containerId = "";
  if (type === 'location') containerId = "locationPillsContainer";
  else if (type === 'arrangement') containerId = "workArrangementContainer";
  else if (type === 'experience') containerId = "experienceLevelContainer";
  else if (type === 'industry') containerId = "industryContainer";

  const buttons = document.getElementById(containerId).querySelectorAll("button");
  buttons.forEach(b => {
    if (b.innerText.trim().toLowerCase() === val.toLowerCase() && b.classList.contains("active-pill")) {
      b.classList.remove("active-pill");
    }
  });

  if (type === 'location') {
    appState.filters.locations = appState.filters.locations.filter(v => v !== val);
  } else if (type === 'arrangement') {
    appState.filters.work_arrangements = appState.filters.work_arrangements.filter(v => v !== val);
  } else if (type === 'experience') {
    appState.filters.experience_levels = appState.filters.experience_levels.filter(v => v !== val);
  } else if (type === 'industry') {
    appState.filters.industries = appState.filters.industries.filter(v => v !== val);
  }

  updateActiveFilterTags();
}

function getVerificationBadge(status, verifiedAt) {
  const stat = status || 'Verified Job';
  const vDate = verifiedAt ? `Verified: ${verifiedAt}` : 'Verified recently';
  if (stat === 'Verified Job') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center space-x-1" title="${vDate}"><i data-lucide="check-circle" class="w-3 h-3 text-emerald-400"></i><span>Verified</span></span>`;
  } else if (stat === 'Potentially Suspicious') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center space-x-1" title="Security Warning: Potential fraud signals detected"><i data-lucide="alert-triangle" class="w-3 h-3 text-rose-400"></i><span>Suspicious</span></span>`;
  } else if (stat === 'Expired / Unavailable') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700 flex items-center space-x-1" title="Posting expired / no longer active"><i data-lucide="archive" class="w-3 h-3 text-slate-500"></i><span>Expired</span></span>`;
  }
  return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center space-x-1" title="Verification Pending"><i data-lucide="clock" class="w-3 h-3 text-amber-400"></i><span>Pending</span></span>`;
}

function getVisaBadge(visaStatus, isInternational) {
  const stat = visaStatus || 'Visa Requirements Unclear';
  if (!isInternational || stat.includes('Domestic')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">Domestic (India)</span>`;
  }
  if (stat === 'Visa Sponsorship Available') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center space-x-1"><i data-lucide="globe" class="w-3 h-3 text-emerald-400"></i><span>Visa Sponsorship</span></span>`;
  }
  if (stat === 'Existing Work Authorisation Required') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30">Work Auth Required</span>`;
  }
  if (stat === 'Visa Sponsorship Required') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">Visa Required</span>`;
  }
  if (stat === 'Sponsorship Unavailable') {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700">No Sponsorship</span>`;
  }
  return `<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">Visa Unclear</span>`;
}

function getSourceBadge(source) {
  const s = source || 'Verified';
  const lower = s.toLowerCase();
  if (lower.includes('linkedin')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-[#0A66C2]/20 text-[#38bdf8] border border-[#0A66C2]/40 flex items-center space-x-1"><svg class="w-3 h-3 fill-current inline-block" viewBox="0 0 24 24"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg><span>LinkedIn MCP</span></span>`;
  }
  if (lower.includes('indeed')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-[#2164f3]/20 text-[#60a5fa] border border-[#2164f3]/40 flex items-center space-x-1"><span>Indeed</span></span>`;
  }
  if (lower.includes('naukri')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center space-x-1"><span>Naukri.com</span></span>`;
  }
  if (lower.includes('glassdoor')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">Glassdoor</span>`;
  }
  if (lower.includes('wellfound') || lower.includes('angellist')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">Wellfound</span>`;
  }
  if (lower.includes('flexjobs')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">FlexJobs</span>`;
  }
  if (lower.includes('dice')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-red-500/20 text-red-300 border border-red-500/40">Dice</span>`;
  }
  if (lower.includes('remotely') || lower.includes('weworkremotely')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-orange-500/20 text-orange-300 border border-orange-500/40">WeWorkRemotely</span>`;
  }
  if (lower.includes('remote ok')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-pink-500/20 text-pink-300 border border-pink-500/40">Remote OK</span>`;
  }
  if (lower.includes('foundit')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">Foundit</span>`;
  }
  if (lower.includes('instahyre')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-green-500/20 text-green-300 border border-green-500/40">Instahyre</span>`;
  }
  if (lower.includes('iimjobs') || lower.includes('hirist')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/40">${escapeHtml(s)}</span>`;
  }
  if (lower.includes('cutshort')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/40">Cutshort</span>`;
  }
  if (lower.includes('shine') || lower.includes('timesjobs') || lower.includes('apna')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-yellow-500/20 text-yellow-300 border border-yellow-500/40">${escapeHtml(s)}</span>`;
  }
  if (lower.includes('upwork')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-600/20 text-emerald-300 border border-emerald-600/40">Upwork</span>`;
  }
  if (lower.includes('toptal')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-600/20 text-blue-300 border border-blue-600/40">Toptal</span>`;
  }
  if (lower.includes('fiverr') || lower.includes('freelancer')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">${escapeHtml(s)}</span>`;
  }
  if (lower.includes('eurojobs') || lower.includes('eures') || lower.includes('stepstone') || lower.includes('totaljobs') || lower.includes('reed') || lower.includes('cv-library') || lower.includes('otta')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-violet-500/20 text-violet-300 border border-violet-500/40">${escapeHtml(s)}</span>`;
  }
  if (lower.includes('remotive')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">Remotive</span>`;
  }
  if (lower.includes('arbeitnow')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-teal-500/15 text-teal-300 border border-teal-500/30">Arbeitnow</span>`;
  }
  if (lower.includes('jobicy')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">Jobicy</span>`;
  }
  if (lower.includes('career portal') || lower.includes('portal') || lower.includes('careers')) {
    return `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">Career Portal</span>`;
  }
  return `<span class="px-2 py-0.5 rounded text-[10px] text-slate-400 bg-slate-800 border border-slate-700 font-medium">${escapeHtml(s)}</span>`;
}

function resetAllFilters() {
  // Reset pills to defaults (empty)
  appState.filters.locations = [];
  appState.filters.work_arrangements = [];
  appState.filters.experience_levels = [];
  appState.filters.industries = [];
  appState.filters.companies = [];
  appState.filters.custom_locations = [];
  appState.filters.custom_industries = [];

  // Update DOM pills
  syncPillsWithState('locationPillsContainer', appState.filters.locations);
  syncPillsWithState('workArrangementContainer', appState.filters.work_arrangements);
  syncPillsWithState('experienceLevelContainer', appState.filters.experience_levels);
  syncPillsWithState('industryContainer', appState.filters.industries);

  document.getElementById("inputVisa").value = "any";
  document.getElementById("inputMinScore").value = 40;
  document.getElementById("minScoreDisplay").innerText = "40%";
  document.getElementById("inputCompanies").value = "";

  updateActiveFilterTags();
  if (appState.jobs && appState.jobs.length > 0) {
    if (appState.resultsView === 'grid') renderGridView();
    else if (appState.resultsView === 'table') renderTableView();
    else renderJobCards();
  }
  showToast("Filters reset to default");
}

function syncPillsWithState(containerId, activeList) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const lowerList = activeList.map(a => a.toLowerCase());
  container.querySelectorAll("button").forEach(b => {
    const text = b.innerText.trim().toLowerCase();
    if (lowerList.includes(text)) {
      b.classList.add("active-pill");
    } else {
      b.classList.remove("active-pill");
    }
  });
}

// ============================================================================
// JOB SEARCH & RANKING
// ============================================================================

async function runJobSearch() {
  const btn = document.getElementById("searchJobsBtn");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Analyzing...</span>`;
  lucide.createIcons();

  const keywords = document.getElementById("inputKeywords").value.trim();
  const companiesStr = document.getElementById("inputCompanies").value.trim();
  const companies = companiesStr ? companiesStr.split(",").map(c => c.trim()).filter(Boolean) : [];
  const visaReq = document.getElementById("inputVisa").value;
  const verificationFilter = document.getElementById("inputVerificationFilter") ? document.getElementById("inputVerificationFilter").value : "all";
  const minScore = parseInt(document.getElementById("inputMinScore").value, 10);
  const maxResults = parseInt(document.getElementById("inputMaxResults").value, 10);

  const payload = {
    keywords: keywords,
    locations: appState.filters.locations,
    location: appState.filters.locations.join(", "),
    work_arrangements: appState.filters.work_arrangements,
    remote_only: appState.filters.work_arrangements.length === 1 && appState.filters.work_arrangements[0] === 'remote',
    experience_levels: appState.filters.experience_levels,
    industries: appState.filters.industries,
    companies: companies,
    sources: appState.filters.sources || ['linkedin', 'indeed', 'remote_boards', 'curated'],
    visa_requirement: visaReq,
    verification_filter: verificationFilter,
    min_score: minScore,
    max_results: maxResults
  };

  try {
    const res = await authFetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (data.success) {
      appState.jobs = data.jobs || [];
      document.getElementById("resultsCountLabel").innerText = `${appState.jobs.length} Jobs Found`;
      showToast(`Found ${appState.jobs.length} matching jobs`);
      
      if (appState.resultsView === 'grid') {
        renderGridView();
      } else if (appState.resultsView === 'table') {
        renderTableView();
      } else {
        renderJobCards();
      }

      // Automatically select first job
      if (appState.jobs.length > 0) {
        selectJob(appState.jobs[0].id);
      } else {
        document.getElementById("noJobSelectedPlaceholder").classList.remove("hidden");
        document.getElementById("jobDetailContent").classList.add("hidden");
      }
    } else {
      showToast(data.detail || "Search failed", true);
    }
  } catch (err) {
    showToast("Error searching jobs: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="search-check" class="w-4 h-4"></i><span>Search Jobs</span>`;
    lucide.createIcons();
  }
}

// ============================================================================
// SPLIT VIEW RENDERING
// ============================================================================

function renderJobCards() {
  const container = document.getElementById("jobCardsListContainer");
  const emptyState = document.getElementById("jobListEmptyState");

  if (!appState.jobs || appState.jobs.length === 0) {
    container.innerHTML = "";
    if (emptyState) container.appendChild(emptyState);
    return;
  }

  const jobsToRender = appState.jobs;
  container.innerHTML = "";

  jobsToRender.forEach(job => {
    const match = job.match || {};
    const score = match.match_score || 50;
    const isStrong = score >= 75;
    const badgeColor = isStrong 
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" 
      : (score >= 60 ? "bg-blue-500/10 text-blue-400 border-blue-500/30" : "bg-amber-500/10 text-amber-400 border-amber-500/30");

    const arrangementBadge = job.is_remote 
      ? '<span class="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800 text-[10px] font-medium">Remote</span>'
      : '<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-medium">Onsite / Hybrid</span>';

    const initials = job.company_initials || (job.company ? job.company.substring(0, 2).toUpperCase() : 'CO');
    const logoGrad = job.company_logo_color || 'from-emerald-600 to-teal-500';
    const rating = job.rating || 4.7;
    const reviews = job.reviews_count || 120;
    const isTracked = appState.tracker.items.some(t => t.job_id === job.id);

    const skillsRow = (job.required_skills || []).slice(0, 3).map(s => 
      `<span class="px-2 py-0.5 rounded bg-slate-950 text-slate-300 text-[10px] font-medium border border-slate-800">${escapeHtml(s)}</span>`
    ).join('');

    const card = document.createElement("div");
    card.id = `card_${job.id}`;
    card.className = `job-card p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 cursor-pointer space-y-3 relative transition-all shadow-md ${appState.selectedJobId === job.id ? 'active-card' : ''}`;
    
    card.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div class="flex items-start space-x-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr ${logoGrad} flex items-center justify-center font-bold text-white text-xs shadow shrink-0">
            ${initials}
          </div>
          <div class="space-y-0.5">
            <h3 class="text-sm font-bold text-white hover:text-emerald-400 transition-colors line-clamp-1">${escapeHtml(job.title)}</h3>
            <div class="flex items-center space-x-2 text-xs text-slate-400">
              <span class="font-semibold text-slate-200">${escapeHtml(job.company)}</span>
              <span class="flex items-center space-x-1 text-amber-400 font-bold text-[11px]">
                <i data-lucide="star" class="w-3 h-3 fill-amber-400"></i>
                <span>${rating}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="flex items-center space-x-1.5 shrink-0">
          <button onclick="toggleTrackJob('${job.id}', event)" class="p-1.5 rounded-lg hover:bg-slate-800 text-${isTracked ? 'emerald-400' : 'slate-500'} hover:text-emerald-400 transition-colors" title="${isTracked ? 'Saved in Tracker' : 'Save to Tracker'}">
            <i data-lucide="bookmark" class="w-4 h-4 ${isTracked ? 'fill-emerald-400 text-emerald-400' : ''}"></i>
          </button>
          <span class="px-2 py-0.5 rounded-full text-xs font-bold border ${badgeColor} whitespace-nowrap">
            ${score}%
          </span>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
        <span class="flex items-center space-x-1 text-slate-200 font-medium">
          <span>${job.country_flag || '📍'}</span>
          <span>${escapeHtml(job.country || job.location || 'Multiple')}</span>
        </span>
        <span>•</span>
        <span class="font-medium text-emerald-300">${escapeHtml(job.salary || 'Competitive')}</span>
        <span>•</span>
        <span class="text-slate-400">${escapeHtml(job.experience_range || '3–5 years')}</span>
      </div>

      <div class="flex flex-wrap items-center gap-1.5 pt-0.5">
        ${getVerificationBadge(job.verification_status, job.verified_at)}
        ${getVisaBadge(job.visa_status, job.is_international)}
        ${skillsRow}
      </div>

      <div class="flex items-center justify-between pt-1 text-[11px] border-t border-slate-800/60">
        <div class="flex items-center space-x-2">
          ${arrangementBadge}
          <span class="text-[10px] ${job.is_apply_disabled ? 'text-slate-500' : 'text-emerald-400'} font-medium">
            ${job.is_apply_disabled ? 'Link unavailable' : (job.recruiter_active || 'Active today')}
          </span>
        </div>
        ${getSourceBadge(job.source)}
      </div>
    `;

    card.onclick = () => selectJob(job.id);
    container.appendChild(card);
  });

  lucide.createIcons();
}

function renderGridView() {
  const container = document.getElementById("gridViewContainer");
  if (!container) return;

  if (!appState.jobs || appState.jobs.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <i data-lucide="briefcase" class="w-10 h-10 mx-auto text-slate-600 mb-2"></i>
        <p class="text-sm font-semibold text-slate-300">No jobs to display in grid view</p>
        <p class="text-xs text-slate-500 mt-1">Run a search to explore opportunities.</p>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  const jobsToRender = appState.jobs;
  container.innerHTML = "";

  jobsToRender.forEach(job => {
    const match = job.match || {};
    const score = match.match_score || 50;
    const isStrong = score >= 75;
    const badgeColor = isStrong 
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" 
      : (score >= 60 ? "bg-blue-500/10 text-blue-400 border-blue-500/30" : "bg-amber-500/10 text-amber-400 border-amber-500/30");

    const initials = job.company_initials || (job.company ? job.company.substring(0, 2).toUpperCase() : 'CO');
    const logoGrad = job.company_logo_color || 'from-emerald-600 to-teal-500';
    const rating = job.rating || 4.7;
    const reviews = job.reviews_count || 120;
    const isTracked = appState.tracker.items.some(t => t.job_id === job.id);

    const skillsRow = (job.required_skills || []).slice(0, 4).map(s => 
      `<span class="px-2 py-0.5 rounded bg-slate-950 text-slate-300 text-[10px] font-medium border border-slate-800">${escapeHtml(s)}</span>`
    ).join('');

    const card = document.createElement("div");
    card.className = "job-card p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-emerald-500/50 cursor-pointer space-y-4 transition-all shadow-xl hover:-translate-y-1 flex flex-col justify-between";
    
    card.innerHTML = `
      <div class="space-y-3">
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center space-x-3">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-tr ${logoGrad} flex items-center justify-center font-bold text-white text-sm shadow-md shrink-0">
              ${initials}
            </div>
            <div>
              <div class="flex items-center space-x-1.5 text-xs text-slate-400">
                <span class="font-bold text-white">${escapeHtml(job.company)}</span>
                <span>•</span>
                <span class="flex items-center text-amber-400 font-semibold"><i data-lucide="star" class="w-3 h-3 fill-amber-400 mr-0.5"></i>${rating}</span>
              </div>
              <h3 class="text-base font-bold text-white hover:text-emerald-400 transition-colors line-clamp-1 mt-0.5">${escapeHtml(job.title)}</h3>
            </div>
          </div>
          <button onclick="toggleTrackJob('${job.id}', event)" class="p-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-${isTracked ? 'emerald-400' : 'slate-500'} hover:text-emerald-400 transition-colors border border-slate-800" title="${isTracked ? 'Saved' : 'Save'}">
            <i data-lucide="bookmark" class="w-4 h-4 ${isTracked ? 'fill-emerald-400 text-emerald-400' : ''}"></i>
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs">
          <span class="px-2.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 font-semibold border border-emerald-500/20">${escapeHtml(job.salary || 'Competitive')}</span>
          <span class="px-2.5 py-0.5 rounded-md bg-slate-800 text-slate-300 font-medium">${escapeHtml(job.location || 'Multiple')}</span>
          <span class="px-2.5 py-0.5 rounded-md ${job.is_remote ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800' : 'bg-slate-800 text-slate-300'} font-medium text-[11px]">${job.is_remote ? 'Remote' : 'Hybrid/Onsite'}</span>
          ${getSourceBadge(job.source)}
        </div>

        <p class="text-xs text-slate-400 line-clamp-2 leading-relaxed">${escapeHtml(job.description ? job.description.substring(0, 140) + '...' : '')}</p>

        ${skillsRow ? `<div class="flex flex-wrap items-center gap-1.5 pt-1">${skillsRow}</div>` : ''}
      </div>

      <div class="pt-3 border-t border-slate-800 flex items-center justify-between mt-2">
        <span class="px-2.5 py-0.5 rounded-full text-xs font-bold border ${badgeColor}">
          ${score}% Match
        </span>
        <button onclick="openJobInSplitView('${job.id}')" class="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-md shadow-emerald-700/20 flex items-center space-x-1.5 transition-all">
          <span>Review & Apply</span>
          <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
        </button>
      </div>
    `;

    card.onclick = () => openJobInSplitView(job.id);
    container.appendChild(card);
  });

  lucide.createIcons();
}

async function toggleTrackJob(jobId, event) {
  if (event) event.stopPropagation();
  const job = appState.jobs.find(j => j.id === jobId);
  if (!job) return;

  const existing = appState.tracker.items.find(t => t.job_id === jobId);
  if (existing) {
    try {
      const res = await authFetch(`/api/tracker/${existing.id}`, { method: "DELETE" });
      if (res.status === 401) {
        showToast("Please sign in to manage your tracker", true);
        openAuthModal("login");
        return;
      }
      const data = await res.json();
      if (data.success) {
        showToast(`Removed ${job.title} from Tracker`);
        await loadTrackerData();
        renderJobCards();
        if (appState.resultsView === 'grid') renderGridView();
        if (appState.selectedJobId === jobId) selectJob(jobId);
      }
    } catch (e) {
      showToast("Failed to remove from tracker", true);
    }
  } else {
    try {
      const res = await authFetch("/api/tracker/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          job_title: job.title,
          company: job.company,
          location: job.location,
          salary: job.salary,
          application_link: job.application_link || "",
          original_url: job.original_url || job.application_link || "",
          source: job.source || "",
          verification_status: job.verification_status || "Verified Job",
          verified_at: job.verified_at || "",
          verification_source: job.verification_source || "",
          visa_status: job.visa_status || job.visa_sponsorship || "",
          country: job.country || "",
          is_apply_disabled: job.is_apply_disabled || false,
          apply_status_text: job.apply_status_text || "",
          recruiter_email: job.recruiter_email || "",
          status: "Saved"
        })
      });
      if (res.status === 401) {
        showToast("Please sign in or create an account to save jobs", true);
        openAuthModal("login");
        return;
      }
      const data = await res.json();
      if (data.success) {
        showToast(`Saved ${job.title} to Tracker!`);
        await loadTrackerData();
        renderJobCards();
        if (appState.resultsView === 'grid') renderGridView();
        if (appState.selectedJobId === jobId) selectJob(jobId);
      }
    } catch (e) {
      showToast("Failed to save to tracker", true);
    }
  }
}

function selectJob(jobId) {
  appState.selectedJobId = jobId;
  const job = appState.jobs.find(j => j.id === jobId);
  if (!job) return;

  // Update card active class
  document.querySelectorAll(".job-card").forEach(c => c.classList.remove("active-card"));
  const activeCard = document.getElementById(`card_${jobId}`);
  if (activeCard) activeCard.classList.add("active-card");

  // Show details panel
  document.getElementById("noJobSelectedPlaceholder").classList.add("hidden");
  const detailContent = document.getElementById("jobDetailContent");
  detailContent.classList.remove("hidden");

  // Company avatar
  const avatar = document.getElementById("detailCompanyAvatar");
  if (avatar) {
    avatar.innerText = job.company_initials || (job.company ? job.company.substring(0, 2).toUpperCase() : 'CO');
    avatar.className = `w-12 h-12 rounded-xl bg-gradient-to-tr ${job.company_logo_color || 'from-emerald-600 to-teal-500'} flex items-center justify-center font-bold text-white text-base shadow-md shrink-0`;
  }

  // Populate header
  document.getElementById("detailTitle").innerText = job.title;
  document.getElementById("detailCompany").innerText = job.company;
  if (document.getElementById("detailRating")) document.getElementById("detailRating").innerText = job.rating || "4.8";
  if (document.getElementById("detailReviews")) document.getElementById("detailReviews").innerText = `(${job.reviews_count || 120} reviews)`;
  document.getElementById("detailLocation").innerText = job.location || "Multiple";
  document.getElementById("detailArrangement").innerText = job.is_remote ? "Remote" : "Onsite / Hybrid";
  document.getElementById("detailSalary").innerText = job.salary || "Competitive Salary";
  document.getElementById("detailVisa").innerText = job.visa_status || job.visa_sponsorship || "Visa Requirements Unclear";
  document.getElementById("detailEmploymentType").innerText = job.employment_type || "Full-time";
  if (document.getElementById("detailExperience")) document.getElementById("detailExperience").innerText = job.experience_range || "3–5 years";
  
  // Country badge
  if (document.getElementById("detailCountryBadge")) {
    document.getElementById("detailCountryFlag").innerText = job.country_flag || "📍";
    document.getElementById("detailCountryName").innerText = job.country || job.location || "Location";
  }

  // Verification badges & trust panel
  if (document.getElementById("detailVerificationBadge")) {
    const vStat = job.verification_status || "Verified Job";
    const verEl = document.getElementById("detailVerificationBadge");
    verEl.innerText = vStat;
    if (vStat === "Verified Job") {
      verEl.className = "px-2.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40";
    } else if (vStat === "Potentially Suspicious") {
      verEl.className = "px-2.5 py-0.5 rounded-md bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40";
    } else if (vStat === "Expired / Unavailable") {
      verEl.className = "px-2.5 py-0.5 rounded-md bg-slate-800 text-slate-400 font-bold border border-slate-700";
    } else {
      verEl.className = "px-2.5 py-0.5 rounded-md bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40";
    }
  }

  if (document.getElementById("detailVerificationStatusPill")) {
    document.getElementById("detailVerificationStatusPill").innerText = job.verification_status || "Verified Job";
  }
  if (document.getElementById("detailVerifiedDate")) {
    document.getElementById("detailVerifiedDate").innerText = job.verified_at ? `Verified: ${job.verified_at}` : 'Verified recently';
  }
  if (document.getElementById("detailVerifiedSource")) {
    document.getElementById("detailVerifiedSource").innerText = job.verification_source || `${job.source || 'Direct'} Verified Posting`;
  }

  if (document.getElementById("detailVisaStatusSummary")) {
    document.getElementById("detailVisaStatusSummary").innerText = job.visa_status || "Visa Requirements Unclear";
  }

  // Exact Apply Link Handling (Requirement 1)
  const applyLink = document.getElementById("detailApplyLink");
  if (applyLink) {
    if (job.is_apply_disabled || !job.application_link || job.application_link === "#" || job.application_link === "") {
      applyLink.href = "javascript:void(0)";
      applyLink.removeAttribute("target");
      applyLink.className = "px-3.5 py-1.5 rounded-lg bg-slate-800 text-slate-400 border border-slate-700 text-xs font-semibold flex items-center space-x-1.5 cursor-not-allowed opacity-80";
      const statusLabel = job.apply_status_text || (job.is_expired ? "Posting Expired" : "Application link unavailable");
      applyLink.innerHTML = `<i data-lucide="ban" class="w-3.5 h-3.5 text-slate-400"></i><span>${escapeHtml(statusLabel)}</span>`;
      applyLink.onclick = (e) => {
        e.preventDefault();
        showToast(job.is_expired ? "This job posting has expired or is no longer accepting applications." : "Direct application URL unavailable for this listing. Contact recruiter via email draft or check verified career portal.", true);
      };
    } else {
      applyLink.href = job.application_link;
      applyLink.target = "_blank";
      applyLink.rel = "noopener noreferrer";
      const src = job.source || "Site";
      if (src.toLowerCase().includes("linkedin")) {
        applyLink.className = "px-3.5 py-1.5 rounded-lg bg-[#0A66C2] hover:bg-[#004182] text-white font-semibold text-xs flex items-center space-x-1.5 shadow-md shadow-[#0A66C2]/30 transition-all";
        applyLink.innerHTML = `<svg class="w-3.5 h-3.5 fill-current inline-block" viewBox="0 0 24 24"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg><span>Apply on LinkedIn</span><i data-lucide="external-link" class="w-3.5 h-3.5"></i>`;
      } else {
        applyLink.className = "px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-1.5 shadow-md shadow-emerald-700/20 transition-all";
        applyLink.innerHTML = `<span>Apply on ${escapeHtml(src)}</span><i data-lucide="external-link" class="w-3.5 h-3.5"></i>`;
      }
      applyLink.onclick = null;
    }
  }

  // Hiring Team insights
  if (document.getElementById("detailRecruiterName")) document.getElementById("detailRecruiterName").innerText = job.recruiter_name || "Talent Acquisition Partner";
  if (document.getElementById("detailRecruiterActive")) document.getElementById("detailRecruiterActive").innerText = job.recruiter_active || "Active today";
  if (document.getElementById("detailInterviewDifficulty")) document.getElementById("detailInterviewDifficulty").innerText = job.interview_difficulty || "Medium (3.2 / 5.0)";
  if (document.getElementById("detailCompanyBenefits")) {
    document.getElementById("detailCompanyBenefits").innerText = (job.benefits || ["Comprehensive Health", "Remote Stipend", "Visa Support"]).slice(0, 3).join(" · ");
  }

  // Sync bookmark button
  const trackBtn = document.getElementById("detailTrackBtn");
  if (trackBtn) {
    const isSaved = appState.tracker.items.some(t => t.job_id === jobId);
    trackBtn.innerHTML = `<i data-lucide="bookmark" class="w-4 h-4 ${isSaved ? 'fill-emerald-400 text-emerald-400' : ''}"></i>`;
    trackBtn.title = isSaved ? "Saved in Tracker (Click to remove)" : "Save to Tracker";
    trackBtn.onclick = (e) => toggleTrackJob(jobId, e);
  }

  // Score badge
  const score = job.match?.match_score || 50;
  const matchBadge = document.getElementById("detailMatchBadge");
  matchBadge.innerText = `${score}% Match`;
  matchBadge.className = `text-xs font-bold px-2.5 py-0.5 rounded-full border ${score >= 75 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'}`;
  document.getElementById("detailMatchScorePercent").innerText = `Overall Match: ${score}%`;

  // Filename guarantee
  const originalFilename = appState.currentResume?.original_filename || appState.currentResume?.file_name || "No resume attached";
  document.getElementById("detailAttachmentFilename").innerText = originalFilename;

  // Match & gap breakdown
  document.getElementById("detailWhyRelevant").innerText = job.match?.why_relevant || "Role matches candidate's core background.";
  
  // Matched skills chips
  const matchedContainer = document.getElementById("detailMatchedSkills");
  matchedContainer.innerHTML = "";
  const matchedList = job.match?.matched_skills || [];
  if (matchedList.length > 0) {
    matchedList.forEach(s => {
      const chip = document.createElement("span");
      chip.className = "px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 text-[10px] border border-emerald-800 font-medium";
      chip.innerText = s;
      matchedContainer.appendChild(chip);
    });
  } else {
    matchedContainer.innerHTML = `<span class="text-slate-500 text-[11px]">Core software engineering foundation</span>`;
  }

  // Missing skills chips
  const missingContainer = document.getElementById("detailMissingSkills");
  missingContainer.innerHTML = "";
  const missingList = job.match?.missing_skills || [];
  if (missingList.length > 0) {
    missingList.forEach(s => {
      const chip = document.createElement("span");
      chip.className = "px-2 py-0.5 rounded bg-amber-950/40 text-amber-300 text-[10px] border border-amber-800 font-medium";
      chip.innerText = s;
      missingContainer.appendChild(chip);
    });
  } else {
    missingContainer.innerHTML = `<span class="text-slate-500 text-[11px]">No critical requirements missing</span>`;
  }

  // AI Email Assistant fields
  const draft = job.email_draft || {};
  document.getElementById("detailDraftTo").value = draft.to_email || job.recruiter_email || "hiring@company.com";
  document.getElementById("detailDraftSubject").value = draft.subject || `Application: ${job.title} - Candidate`;
  document.getElementById("detailDraftBody").value = draft.body || "";
  document.getElementById("detailDraftStatus").innerText = job.draft_status || "Draft Prepared";

  // Signature preview
  const verifiedName = appState.gmail.full_name || appState.currentResume?.name || "Candidate";
  document.getElementById("detailSignaturePreview").innerText = verifiedName;

  // Gmail Web direct link
  const gmailWebUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(draft.to_email || '')}&su=${encodeURIComponent(draft.subject || '')}&body=${encodeURIComponent(draft.body || '')}`;
  document.getElementById("detailGmailWebLink").href = gmailWebUrl;

  // Full Description
  document.getElementById("detailFullDesc").innerText = job.description || "No full description provided.";

  lucide.createIcons();
}

// ============================================================================
// TABLE VIEW RENDERING
// ============================================================================

function renderTableView() {
  const tbody = document.getElementById("tableViewBody");
  if (!tbody) return;

  if (!appState.jobs || appState.jobs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-12 text-center text-slate-500">No jobs searched yet.</td></tr>`;
    return;
  }

  const jobsToRender = appState.jobs;
  tbody.innerHTML = "";

  jobsToRender.forEach(job => {
    const score = job.match?.match_score || 50;
    const isStrong = score >= 75;
    const badgeColor = isStrong ? "text-emerald-400 font-bold" : "text-blue-400 font-semibold";

    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/50 transition-colors";
    tr.innerHTML = `
      <td class="py-3 px-4 font-semibold text-white">
        <a href="javascript:void(0)" onclick="openJobInSplitView('${job.id}')" class="hover:text-emerald-400 hover:underline">
          ${escapeHtml(job.title)}
        </a>
      </td>
      <td class="py-3 px-4 text-slate-300 font-medium">
        <div>${escapeHtml(job.company)}</div>
        <div class="pt-0.5">${getSourceBadge(job.source)}</div>
      </td>
      <td class="py-3 px-4 text-slate-400">${escapeHtml(job.location || 'Multiple')}</td>
      <td class="py-3 px-4 text-slate-400 font-mono">${escapeHtml(job.salary || 'Competitive')}</td>
      <td class="py-3 px-4 ${badgeColor}">${score}%</td>
      <td class="py-3 px-4">
        <span class="px-2 py-0.5 rounded-full bg-slate-800 text-[11px] text-slate-300 border border-slate-700">
          ${escapeHtml(job.draft_status || 'Draft Prepared')}
        </span>
      </td>
      <td class="py-3 px-4 text-right space-x-1.5 whitespace-nowrap">
        <button onclick="openJobInSplitView('${job.id}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium">Review</button>
        <button onclick="quickDraftJob('${job.id}')" class="px-2.5 py-1 rounded bg-blue-950/60 hover:bg-blue-900 border border-blue-800 text-blue-300 text-xs font-medium" title="Save draft in Gmail">Draft</button>
        <a href="${job.application_link || '#'}" target="_blank" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs" title="Apply on ${escapeHtml(job.source || 'Site')}"><i data-lucide="external-link" class="w-3.5 h-3.5 inline"></i></a>
      </td>
    `;
    tbody.appendChild(tr);
  });

  lucide.createIcons();
}

function openJobInSplitView(jobId) {
  switchResultsView('split');
  selectJob(jobId);
}

function filterTableViewRows() {
  const query = document.getElementById("tableSearchInput").value.toLowerCase();
  const rows = document.getElementById("tableViewBody").querySelectorAll("tr");
  rows.forEach(r => {
    const text = r.innerText.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}

// ============================================================================
// EMAIL ASSISTANT ACTIONS (OPTION A & OPTION B)
// ============================================================================

// OPTION A: Create Gmail Draft
async function handleOptionADraft() {
  if (!appState.selectedJobId) {
    showToast("Please select a job first", true);
    return;
  }

  const job = appState.jobs.find(j => j.id === appState.selectedJobId);
  if (!job) return;

  const toEmail = document.getElementById("detailDraftTo").value.trim();
  const subject = document.getElementById("detailDraftSubject").value.trim();
  const body = document.getElementById("detailDraftBody").value.trim();

  const btn = document.getElementById("btnOptionADraft");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Saving Draft...</span>`;
  lucide.createIcons();

  try {
    const res = await authFetch("/api/gmail/create-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        to_email: toEmail,
        subject: subject,
        body: body,
        attach_resume: true
      })
    });

    if (res.status === 401) {
      showToast("Please sign in or create an account to create Gmail drafts.", true);
      openAuthModal("login");
      return;
    }

    const data = await res.json();

    if (data.success) {
      showToast(data.message || "Draft created in your Gmail Drafts folder!");
      job.draft_status = `Draft Created in Gmail (${data.draft_id?.slice(0, 8)})`;
      document.getElementById("detailDraftStatus").innerText = job.draft_status;
      loadTrackerData();
    } else {
      showToast(data.detail || "Failed to create draft in Gmail", true);
    }
  } catch (err) {
    showToast("Error creating Gmail draft: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="inbox" class="w-4 h-4 text-blue-400"></i><span>Option A: Create Gmail Draft</span>`;
    lucide.createIcons();
  }
}

// OPTION B: Send Email Directly (With explicit confirmation modal)
function openSendConfirmModal() {
  if (!appState.selectedJobId) {
    showToast("Please select a job first", true);
    return;
  }

  const job = appState.jobs.find(j => j.id === appState.selectedJobId);
  if (!job) return;

  const toEmail = document.getElementById("detailDraftTo").value.trim();
  const subject = document.getElementById("detailDraftSubject").value.trim();
  const originalFilename = appState.currentResume?.original_filename || appState.currentResume?.file_name || "--";

  document.getElementById("confirmSendTo").innerText = toEmail || "recruiter@company.com";
  document.getElementById("confirmSendSubject").innerText = subject || `Application: ${job.title}`;
  document.getElementById("confirmSendAttachment").innerText = originalFilename;
  document.getElementById("confirmSendCheck").checked = false;

  document.getElementById("sendConfirmModal").classList.remove("hidden");
  lucide.createIcons();
}

function closeSendConfirmModal() {
  document.getElementById("sendConfirmModal").classList.add("hidden");
}

async function executeDirectSend() {
  const isChecked = document.getElementById("confirmSendCheck").checked;
  if (!isChecked) {
    showToast("Please check the confirmation box to authorize sending", true);
    return;
  }

  const job = appState.jobs.find(j => j.id === appState.selectedJobId);
  if (!job) return;

  const toEmail = document.getElementById("detailDraftTo").value.trim();
  const subject = document.getElementById("detailDraftSubject").value.trim();
  const body = document.getElementById("detailDraftBody").value.trim();

  const sendBtn = document.getElementById("executeSendBtn");
  sendBtn.disabled = true;
  sendBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Sending Directly...</span>`;
  lucide.createIcons();

  try {
    const res = await authFetch("/api/gmail/send-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        to_email: toEmail,
        subject: subject,
        body: body,
        attach_resume: true,
        confirm_send: true
      })
    });

    if (res.status === 401) {
      closeSendConfirmModal();
      showToast("Please sign in or create an account to send emails.", true);
      openAuthModal("login");
      return;
    }

    const data = await res.json();

    if (data.success) {
      closeSendConfirmModal();
      showToast(`Application email sent directly to ${toEmail}!`);
      job.draft_status = `Email Sent Directly (${data.message_id?.slice(0, 8)})`;
      document.getElementById("detailDraftStatus").innerText = job.draft_status;
      loadTrackerData();
    } else {
      showToast(data.detail || "Failed to send email", true);
    }
  } catch (err) {
    showToast("Error sending email: " + err.message, true);
  } finally {
    sendBtn.disabled = false;
    sendBtn.innerHTML = `<i data-lucide="send" class="w-4 h-4"></i><span>Send Email Directly</span>`;
    lucide.createIcons();
  }
}

// Quick draft from table view
async function quickDraftJob(jobId) {
  const job = appState.jobs.find(j => j.id === jobId);
  if (!job) return;

  const draft = job.email_draft || {};
  showToast(`Creating Gmail draft for ${job.title}...`);

  try {
    const res = await authFetch("/api/gmail/create-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        to_email: draft.to_email || job.recruiter_email || "hiring@company.com",
        subject: draft.subject || `Application: ${job.title}`,
        body: draft.body || "Hello,\n\nPlease find my resume attached.\n\nBest regards,",
        attach_resume: true
      })
    });

    if (res.status === 401) {
      showToast("Please sign in or create an account to create drafts.", true);
      openAuthModal("login");
      return;
    }

    const data = await res.json();
    if (data.success) {
      showToast(`Draft created in Gmail for ${job.title}!`);
      job.draft_status = `Draft Created in Gmail`;
      renderTableView();
      loadTrackerData();
    } else {
      showToast(data.detail || "Failed to save draft", true);
    }
  } catch (err) {
    showToast("Error creating draft: " + err.message, true);
  }
}

async function batchSaveToGmailDrafts() {
  if (!appState.jobs || appState.jobs.length === 0) {
    showToast("No jobs to draft. Run a search first.", true);
    return;
  }

  const formData = new FormData();
  formData.append("min_score", "70");
  formData.append("attach_resume", "true");

  showToast("Creating drafts in Gmail for top matching roles...");

  try {
    const res = await authFetch("/api/gmail/batch-draft", {
      method: "POST",
      body: formData
    });

    if (res.status === 401) {
      showToast("Please sign in or create an account to batch create drafts.", true);
      openAuthModal("login");
      return;
    }

    const data = await res.json();
    if (data.success) {
      showToast(data.message);
      loadTrackerData();
    } else {
      showToast(data.detail || "Batch draft failed", true);
    }
  } catch (err) {
    showToast("Error in batch drafting: " + err.message, true);
  }
}

function copyDetailDraft() {
  const body = document.getElementById("detailDraftBody").value;
  navigator.clipboard.writeText(body);
  showToast("Email text copied to clipboard!");
}

async function downloadDetailEml() {
  if (!appState.selectedJobId) return;
  try {
    const res = await authFetch(`/api/draft/download-eml/${appState.selectedJobId}`);
    if (res.status === 401) {
      showToast("Please sign in to download EML file", true);
      openAuthModal("login");
      return;
    }
    if (!res.ok) {
      showToast("Could not download EML draft", true);
      return;
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Application_${appState.selectedJobId}.eml`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    showToast("Error downloading EML: " + err.message, true);
  }
}

function exportToCSV() {
  if (!appState.jobs || appState.jobs.length === 0) {
    showToast("No jobs to export", true);
    return;
  }
  let csv = "Job Title,Company,Location,Salary,Match Score,Application Link,Email Draft Status\n";
  appState.jobs.forEach(j => {
    const title = `"${(j.title || '').replace(/"/g, '""')}"`;
    const company = `"${(j.company || '').replace(/"/g, '""')}"`;
    const loc = `"${(j.location || '').replace(/"/g, '""')}"`;
    const sal = `"${(j.salary || '').replace(/"/g, '""')}"`;
    const score = j.match?.match_score || 0;
    const link = `"${j.application_link || ''}"`;
    const status = `"${(j.draft_status || '').replace(/"/g, '""')}"`;
    csv += `${title},${company},${loc},${sal},${score}%,${link},${status}\n`;
  });

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `JobFlow_AI_Jobs_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}

// ============================================================================
// APPLICATION TRACKER LOGIC
// ============================================================================

async function loadTrackerData() {
  try {
    const res = await authFetch("/api/tracker");
    if (res.status === 401 || !res.ok) {
      appState.tracker.items = [];
      appState.tracker.stats = {};
      updateTrackerKpis({});
      renderTrackerTable();
      return;
    }
    const data = await res.json();
    if (data.success) {
      appState.tracker.items = data.items || [];
      
      const statsRes = await authFetch("/api/tracker/stats");
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        if (statsData.success) {
          appState.tracker.stats = statsData.stats;
          updateTrackerKpis(statsData.stats);
        }
      }

      renderTrackerTable();
    }
  } catch (err) {
    console.error("Error loading tracker data:", err);
  }
}

function updateTrackerKpis(stats) {
  document.getElementById("kpiTotal").innerText = stats.Total || 0;
  document.getElementById("kpiSaved").innerText = stats.Saved || 0;
  document.getElementById("kpiToApply").innerText = stats["To Apply"] || 0;
  document.getElementById("kpiDraftCreated").innerText = stats["Draft Created"] || 0;
  document.getElementById("kpiApplied").innerText = stats.Applied || 0;
  document.getElementById("kpiInterview").innerText = stats.Interview || 0;
  document.getElementById("kpiOffer").innerText = stats.Offer || 0;
  document.getElementById("kpiRejected").innerText = stats.Rejected || 0;
  document.getElementById("navTrackerCount").innerText = stats.Total || 0;
}

function filterTrackerByStatus(status) {
  appState.tracker.activeStatusFilter = status;
  const buttons = document.querySelectorAll(".tracker-filter-btn");
  buttons.forEach(b => {
    if (b.innerText.trim() === status) {
      b.classList.add("active-pill");
    } else {
      b.classList.remove("active-pill");
    }
  });
  renderTrackerTable();
}

function renderTrackerTable() {
  const tbody = document.getElementById("trackerTableBody");
  if (!tbody) return;

  const query = (document.getElementById("trackerSearchInput")?.value || "").toLowerCase();
  const filter = appState.tracker.activeStatusFilter;

  let filtered = appState.tracker.items;
  if (filter !== 'All') {
    filtered = filtered.filter(item => item.status === filter);
  }
  if (query) {
    filtered = filtered.filter(item => 
      (item.job_title || '').toLowerCase().includes(query) ||
      (item.company || '').toLowerCase().includes(query) ||
      (item.location || '').toLowerCase().includes(query)
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-12 text-center text-slate-500">No applications in this category.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";

  const statusOptions = ["Saved", "To Apply", "Draft Created", "Applied", "Interview", "Offer", "Rejected"];

  filtered.forEach(item => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition-colors";

    const optionsHtml = statusOptions.map(st => 
      `<option value="${st}" ${st === item.status ? 'selected' : ''}>${st}</option>`
    ).join("");

    tr.innerHTML = `
      <td class="py-3 px-4">
        <div class="font-bold text-white text-xs">${escapeHtml(item.job_title)}</div>
        <div class="text-[11px] text-slate-400">${escapeHtml(item.company)}</div>
      </td>
      <td class="py-3 px-4 text-xs">
        <div class="text-slate-300">${escapeHtml(item.location || 'Multiple')}</div>
        <div class="text-[11px] text-emerald-400 font-mono">${escapeHtml(item.salary || 'Competitive')}</div>
      </td>
      <td class="py-3 px-4">
        <select onchange="handleTrackerStatusChange('${item.id}', this.value)" class="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white focus:outline-none focus:border-emerald-500">
          ${optionsHtml}
        </select>
      </td>
      <td class="py-3 px-4 text-xs">
        <div class="text-slate-300 font-mono">${escapeHtml(item.recruiter_email || 'Not specified')}</div>
        <div class="text-[10px] text-slate-500">${escapeHtml(item.email_status || 'Draft Prepared')}</div>
      </td>
      <td class="py-3 px-4">
        <input type="date" value="${item.follow_up_date || ''}" onchange="handleTrackerFieldChange('${item.id}', 'follow_up_date', this.value)" class="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-emerald-500">
      </td>
      <td class="py-3 px-4">
        <input type="text" value="${escapeHtml(item.notes || '')}" placeholder="Add note..." onblur="handleTrackerFieldChange('${item.id}', 'notes', this.value)" class="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-300 w-36 focus:outline-none focus:border-emerald-500">
      </td>
      <td class="py-3 px-4 text-right space-x-1.5 whitespace-nowrap">
        ${item.application_link && item.application_link !== '#' && !item.is_apply_disabled ? `<a href="${item.application_link}" target="_blank" rel="noopener noreferrer" class="p-1.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-300 hover:text-white inline-block" title="Open Verified Application Link"><i data-lucide="external-link" class="w-3.5 h-3.5"></i></a>` : `<span class="p-1.5 rounded bg-slate-900 border border-slate-800 text-slate-500 inline-block cursor-not-allowed" title="${escapeHtml(item.apply_status_text || 'Application link unavailable')}"><i data-lucide="ban" class="w-3.5 h-3.5"></i></span>`}
        <button onclick="handleDeleteTrackerItem('${item.id}')" class="p-1.5 rounded bg-slate-800 hover:bg-rose-950 text-slate-400 hover:text-rose-400 transition-colors inline-block" title="Delete"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>
      </td>
    `;

    tbody.appendChild(tr);
  });

  lucide.createIcons();
}

async function handleTrackerStatusChange(itemId, newStatus) {
  try {
    const res = await authFetch(`/api/tracker/${itemId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.status === 401) {
      showToast("Please sign in to update application status", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast(`Status updated to: ${newStatus}`);
      loadTrackerData();
    }
  } catch (err) {
    showToast("Failed to update status", true);
  }
}

async function handleTrackerFieldChange(itemId, field, val) {
  try {
    const payload = {};
    payload[field] = val;
    await authFetch(`/api/tracker/${itemId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error("Error updating field:", err);
  }
}

async function handleDeleteTrackerItem(itemId) {
  try {
    const res = await authFetch(`/api/tracker/${itemId}`, { method: "DELETE" });
    if (res.status === 401) {
      showToast("Please sign in to delete tracker items", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Application removed from tracker");
      loadTrackerData();
    }
  } catch (err) {
    showToast("Failed to delete item", true);
  }
}

async function saveActiveJobToTracker() {
  if (!appState.selectedJobId) return;
  const job = appState.jobs.find(j => j.id === appState.selectedJobId);
  if (!job) return;

  try {
    const res = await authFetch("/api/tracker/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        job_title: job.title,
        company: job.company,
        location: job.location,
        salary: job.salary,
        application_link: job.application_link,
        recruiter_email: job.recruiter_email,
        status: "Saved"
      })
    });
    if (res.status === 401) {
      showToast("Please sign in or create an account to save jobs", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast(`Saved ${job.title} to Tracker!`);
      loadTrackerData();
    }
  } catch (err) {
    showToast("Failed to save job to tracker", true);
  }
}

function openAddTrackerModal() {
  document.getElementById("addTrackerModal").classList.remove("hidden");
  lucide.createIcons();
}

function closeAddTrackerModal() {
  document.getElementById("addTrackerModal").classList.add("hidden");
}

async function saveCustomTrackerItem() {
  const title = document.getElementById("addTrackerTitle").value.trim();
  const company = document.getElementById("addTrackerCompany").value.trim();
  const location = document.getElementById("addTrackerLocation").value.trim();
  const status = document.getElementById("addTrackerStatus").value;
  const recruiter = document.getElementById("addTrackerRecruiterEmail").value.trim();
  const link = document.getElementById("addTrackerLink").value.trim();
  const notes = document.getElementById("addTrackerNotes").value.trim();

  if (!title || !company) {
    showToast("Job Title and Company are required", true);
    return;
  }

  try {
    const res = await authFetch("/api/tracker/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_title: title,
        company: company,
        location: location || "Not specified",
        status: status,
        recruiter_email: recruiter,
        application_link: link || "#",
        notes: notes
      })
    });
    if (res.status === 401) {
      showToast("Please sign in or create an account to add custom applications", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      closeAddTrackerModal();
      showToast("Application added to Tracker!");
      loadTrackerData();
    }
  } catch (err) {
    showToast("Failed to add custom application", true);
  }
}

// ============================================================================
// GMAIL INTEGRATION MODAL (APP PASS / OAUTH)
// ============================================================================

function openGmailModal() {
  document.getElementById("gmailModal").classList.remove("hidden");
  lucide.createIcons();
}

function closeGmailModal() {
  document.getElementById("gmailModal").classList.add("hidden");
}

async function connectWithAppPassword() {
  const email = document.getElementById("appPassEmailInput").value.trim();
  const password = document.getElementById("appPassKeyInput").value.trim();

  if (!email || !password) {
    showToast("Please enter both email and 16-character App Password", true);
    return;
  }

  const btn = document.getElementById("connectAppPassBtn");
  btn.disabled = true;
  btn.innerText = "Connecting...";

  try {
    const res = await authFetch("/api/gmail/connect-app-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_email: email, app_password: password })
    });
    if (res.status === 401) {
      showToast("Please sign in or create an account to connect Gmail", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Gmail connected successfully via App Password!");
      closeGmailModal();
      checkSystemStatus();
    } else {
      showToast(data.detail || "Authentication failed", true);
    }
  } catch (err) {
    showToast("Error connecting: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerText = "Connect Gmail Instantly";
  }
}

async function saveOAuthKeysAndConnect() {
  const cid = document.getElementById("oauthClientIdInput").value.trim();
  const sec = document.getElementById("oauthClientSecretInput").value.trim();

  if (!cid || !sec) {
    showToast("Please enter Client ID and Client Secret", true);
    return;
  }

  try {
    const res = await authFetch("/api/settings/oauth-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: cid, client_secret: sec })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Keys saved. Opening Google sign-in window...");
      const authRes = await authFetch("/api/gmail/connect", { method: "POST" });
      const authData = await authRes.json();
      if (authData.success) {
        showToast("Connected via OAuth: " + authData.email);
        closeGmailModal();
        checkSystemStatus();
      } else {
        showToast(authData.detail || "OAuth failed", true);
      }
    } else {
      showToast(data.detail || "Invalid credentials", true);
    }
  } catch (err) {
    showToast("Error configuring OAuth: " + err.message, true);
  }
}

async function sendTestDraftToGmail() {
  const btn = document.getElementById("testDraftBtn");
  btn.disabled = true;
  btn.innerText = "Creating Test Draft...";

  try {
    const res = await authFetch("/api/gmail/test-draft", { method: "POST" });
    if (res.status === 401) {
      showToast("Please sign in to test Gmail drafts", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Test draft created in your Gmail Drafts folder!");
    } else {
      showToast(data.detail || "Failed to create test draft", true);
    }
  } catch (err) {
    showToast("Error: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="send" class="w-4 h-4"></i><span>Create Test Draft in Your Gmail</span>`;
    lucide.createIcons();
  }
}

async function disconnectGmailAccount() {
  try {
    const res = await authFetch("/api/gmail/disconnect", { method: "POST" });
    if (res.status === 401) {
      showToast("Please sign in to disconnect Gmail", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Gmail disconnected");
      checkSystemStatus();
    }
  } catch (err) {
    showToast("Failed to disconnect", true);
  }
}

// ============================================================================
// SETTINGS MODAL & GEMINI KEY
// ============================================================================

function openSettingsModal() {
  document.getElementById("settingsModal").classList.remove("hidden");
  lucide.createIcons();
}

function closeSettingsModal() {
  document.getElementById("settingsModal").classList.add("hidden");
}

async function saveGeminiKey() {
  const key = document.getElementById("settingsGeminiKeyInput").value.trim();
  if (!key) return;

  try {
    const res = await authFetch("/api/settings/gemini-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gemini_api_key: key })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Gemini API key updated!");
      closeSettingsModal();
      checkSystemStatus();
    }
  } catch (err) {
    showToast("Error saving key", true);
  }
}

// ============================================================================
// TOAST NOTIFICATIONS & UTILS
// ============================================================================

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  const msgEl = document.getElementById("toastMessage");
  const iconEl = document.getElementById("toastIcon");

  if (!toast || !msgEl || !iconEl) return;

  msgEl.innerText = message;
  if (isError) {
    iconEl.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-400"></i>`;
    toast.className = "fixed bottom-6 right-6 z-50 transform transition-all duration-300 flex items-center space-x-3 px-4 py-3 rounded-xl bg-rose-950 border border-rose-800 shadow-2xl text-xs text-white opacity-100 translate-y-0";
  } else {
    iconEl.innerHTML = `<i data-lucide="check" class="w-4 h-4 text-emerald-400"></i>`;
    toast.className = "fixed bottom-6 right-6 z-50 transform transition-all duration-300 flex items-center space-x-3 px-4 py-3 rounded-xl bg-slate-800 border border-slate-700 shadow-2xl text-xs text-white opacity-100 translate-y-0";
  }
  lucide.createIcons();

  setTimeout(() => {
    toast.className = "fixed bottom-6 right-6 z-50 transform translate-y-24 opacity-0 transition-all duration-300 flex items-center space-x-3 px-4 py-3 rounded-xl bg-slate-800 border border-slate-700 shadow-2xl text-xs text-white";
  }, 4000);
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ============================================================================
// AUTOMATED JOB SEARCH SCHEDULER LOGIC
// ============================================================================

async function loadSchedulerData() {
  try {
    const res = await authFetch("/api/scheduler/config");
    if (res.status === 401 || !res.ok) {
      renderSchedulerUI({
        enabled: false,
        frequency: "every_6_hours",
        keywords: "",
        locations: [],
        auto_create_draft: false,
        next_run_time: null,
        last_run_status: "Please sign in to configure autonomous scheduler"
      });
      return;
    }
    const data = await res.json();
    if (data.success && data.config) {
      renderSchedulerUI(data.config);
    }
  } catch (err) {
    console.error("Error loading scheduler data:", err);
  }
}

function renderSchedulerUI(cfg) {
  const isEnabled = cfg.enabled === true;

  // Header / Master toggle
  const statusBadge = document.getElementById("schedulerStatusBadge");
  const toggleBtn = document.getElementById("schedulerMasterToggleBtn");
  const toggleText = document.getElementById("schedulerToggleText");
  const navDot = document.getElementById("navSchedulerDot");

  if (isEnabled) {
    if (statusBadge) {
      statusBadge.innerText = "Running";
      statusBadge.className = "text-xs font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
    }
    if (toggleBtn) {
      toggleBtn.className = "px-5 py-2.5 rounded-xl font-bold text-xs flex items-center space-x-2 transition-all bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/25";
      toggleBtn.innerHTML = `<i data-lucide="pause" class="w-4 h-4"></i><span>Pause Scheduler</span>`;
    }
    if (navDot) navDot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
  } else {
    if (statusBadge) {
      statusBadge.innerText = "Paused";
      statusBadge.className = "text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700";
    }
    if (toggleBtn) {
      toggleBtn.className = "px-5 py-2.5 rounded-xl font-bold text-xs flex items-center space-x-2 transition-all bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/25";
      toggleBtn.innerHTML = `<i data-lucide="play" class="w-4 h-4"></i><span>Start Scheduler</span>`;
    }
    if (navDot) navDot.className = "w-2 h-2 rounded-full bg-slate-600";
  }

  // Cards
  document.getElementById("schedCardStatus").innerText = isEnabled ? "Active (Running)" : "Paused";
  
  const freqLabels = {
    "every_1_hour": "Every 1 Hour",
    "every_2_hours": "Every 2 Hours",
    "every_4_hours": "Every 4 Hours",
    "every_6_hours": "Every 6 Hours",
    "every_12_hours": "Every 12 Hours",
    "daily_24_hours": "Every 24 Hours (Daily)"
  };
  document.getElementById("schedCardFrequency").innerText = freqLabels[cfg.frequency] || "Every 6 Hours";
  document.getElementById("schedCardNextRun").innerText = isEnabled && cfg.next_run_time ? cfg.next_run_time : "Paused";
  document.getElementById("schedCardTotalRuns").innerText = cfg.total_runs || 0;

  // Form controls
  const freqSelect = document.getElementById("schedFrequencySelect");
  if (freqSelect) freqSelect.value = cfg.frequency || "every_6_hours";

  const autoTrackerCheck = document.getElementById("schedAutoTrackerCheck");
  if (autoTrackerCheck) autoTrackerCheck.checked = cfg.auto_save_tracker !== false;

  const autoDraftCheck = document.getElementById("schedAutoDraftCheck");
  if (autoDraftCheck) autoDraftCheck.checked = cfg.auto_create_drafts === true;

  const minScoreSlider = document.getElementById("schedMinScoreSlider");
  const minScoreDisplay = document.getElementById("schedMinScoreDisplay");
  if (minScoreSlider) minScoreSlider.value = cfg.min_score || 65;
  if (minScoreDisplay) minScoreDisplay.innerText = `${cfg.min_score || 65}%`;

  // Search preferences preview
  const prefs = cfg.search_preferences || {};
  document.getElementById("schedPreviewKeywords").innerText = prefs.keywords || document.getElementById("inputKeywords")?.value || "None configured";
  document.getElementById("schedPreviewLocations").innerText = (prefs.locations && prefs.locations.length ? prefs.locations.join(", ") : appState.filters.locations.join(", ")) || "None selected";
  document.getElementById("schedPreviewResume").innerText = appState.currentResume?.original_filename || appState.currentResume?.file_name || "No resume uploaded";
  document.getElementById("schedPreviewLastStatus").innerText = cfg.last_run_status || "Idle";

  // Logs table
  renderSchedulerLogs(cfg.logs || []);

  lucide.createIcons();
}

function renderSchedulerLogs(logs) {
  const tbody = document.getElementById("schedLogsTableBody");
  if (!tbody) return;

  if (!logs || logs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-slate-500">No scheduled runs recorded yet. Click "Run Now" to test.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  logs.forEach(log => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition-colors";
    
    const statusColor = log.status === "Success" 
      ? "text-emerald-400 font-bold" 
      : (log.status === "Skipped" ? "text-amber-400 font-semibold" : "text-rose-400 font-semibold");

    tr.innerHTML = `
      <td class="py-3 px-4 text-slate-300 font-mono text-[11px] whitespace-nowrap">${escapeHtml(log.timestamp)}</td>
      <td class="py-3 px-4 font-semibold text-slate-200">${escapeHtml(log.trigger)}</td>
      <td class="py-3 px-4 text-slate-400 font-mono">${log.jobs_evaluated || 0}</td>
      <td class="py-3 px-4 text-emerald-400 font-bold font-mono">${log.matches_found || 0}</td>
      <td class="py-3 px-4 text-blue-400 font-bold font-mono">${log.drafts_created || 0}</td>
      <td class="py-3 px-4 ${statusColor}">${escapeHtml(log.status)}</td>
      <td class="py-3 px-4 text-slate-400 text-[11px] max-w-xs truncate" title="${escapeHtml(log.summary)}">${escapeHtml(log.summary)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function toggleSchedulerActive() {
  try {
    const res = await authFetch("/api/scheduler/config");
    if (res.status === 401) {
      showToast("Please sign in or create an account to activate the scheduler.", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    const currentEnabled = data.config?.enabled === true;
    const newEnabled = !currentEnabled;

    const updateRes = await authFetch("/api/scheduler/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: newEnabled })
    });
    const updateData = await updateRes.json();
    if (updateData.success) {
      showToast(newEnabled ? "Scheduler started! Periodic search active." : "Scheduler paused.");
      renderSchedulerUI(updateData.config);
    }
  } catch (err) {
    showToast("Error updating scheduler state", true);
  }
}

async function saveSchedulerSettings() {
  const frequency = document.getElementById("schedFrequencySelect").value;
  const autoTracker = document.getElementById("schedAutoTrackerCheck").checked;
  const autoDraft = document.getElementById("schedAutoDraftCheck").checked;
  const minScore = parseInt(document.getElementById("schedMinScoreSlider").value, 10);

  // Sync active search preferences from Find Jobs tab
  const searchKeywords = document.getElementById("inputKeywords")?.value || "";
  const searchPreferences = {
    keywords: searchKeywords,
    locations: appState.filters.locations,
    work_arrangements: appState.filters.work_arrangements,
    experience_levels: appState.filters.experience_levels,
    industries: appState.filters.industries,
    visa_requirement: document.getElementById("inputVisa")?.value || "any"
  };

  try {
    const res = await authFetch("/api/scheduler/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frequency: frequency,
        auto_save_tracker: autoTracker,
        auto_create_drafts: autoDraft,
        min_score: minScore,
        search_preferences: searchPreferences
      })
    });
    if (res.status === 401) {
      showToast("Please sign in or create an account to save scheduler settings.", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast("Scheduler configuration saved!");
      renderSchedulerUI(data.config);
    } else {
      showToast("Failed to save scheduler configuration", true);
    }
  } catch (err) {
    showToast("Error saving scheduler: " + err.message, true);
  }
}

async function runSchedulerNow() {
  const btn = document.getElementById("schedulerRunNowBtn");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Running...</span>`;
  lucide.createIcons();

  showToast("Executing scheduled search & matching cycle...");

  try {
    const res = await authFetch("/api/scheduler/run-now", { method: "POST" });
    if (res.status === 401) {
      showToast("Please sign in or create an account to run the scheduler.", true);
      openAuthModal("login");
      return;
    }
    const data = await res.json();
    if (data.success) {
      showToast(`Automation complete: Found ${data.matches_found} matching roles!`);
      loadSchedulerData();
      loadTrackerData();
    } else {
      showToast(data.message || "Scheduler run completed with warnings", true);
      loadSchedulerData();
    }
  } catch (err) {
    showToast("Error running scheduler: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i><span>Run Now</span>`;
    lucide.createIcons();
  }
}

// ============================================================================
// LINKEDIN MCP INTEGRATION CONTROLLERS
// ============================================================================

function openLinkedInModal() {
  const modal = document.getElementById("linkedinModal");
  if (modal) modal.classList.remove("hidden");
  lucide.createIcons();
}

function closeLinkedInModal() {
  const modal = document.getElementById("linkedinModal");
  if (modal) modal.classList.add("hidden");
}

let lastModalLinkedInJobs = [];

async function testLinkedInModalSearch() {
  const kwInput = document.getElementById("modalLinkedInKeywords");
  const locInput = document.getElementById("modalLinkedInLocation");
  const kw = (kwInput ? kwInput.value.trim() : "") || "Python Developer";
  const loc = (locInput ? locInput.value.trim() : "") || "India";
  const btn = document.getElementById("modalLinkedInSearchBtn");
  const resultsBox = document.getElementById("modalLinkedInResultsBox");
  const countEl = document.getElementById("modalLinkedInResultsCount");
  const listEl = document.getElementById("modalLinkedInJobsList");

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Querying LinkedIn MCP Server...</span>`;
    lucide.createIcons();
  }

  try {
    const res = await authFetch("/api/linkedin/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keywords: kw, location: loc, limit: 10 })
    });
    const data = await res.json();
    if (data.success && data.jobs) {
      lastModalLinkedInJobs = data.jobs;
      if (resultsBox) resultsBox.classList.remove("hidden");
      if (countEl) countEl.innerText = `${data.jobs.length} Verified LinkedIn Jobs Found`;
      if (listEl) {
        listEl.innerHTML = data.jobs.map(j => `
          <div class="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between gap-2 text-xs">
            <div class="truncate">
              <div class="font-bold text-white truncate">${escapeHtml(j.title)}</div>
              <div class="text-[11px] text-slate-400 truncate">${escapeHtml(j.company)} • ${escapeHtml(j.location)} (${escapeHtml(j.work_arrangement)})</div>
            </div>
            <a href="${escapeHtml(j.application_link)}" target="_blank" class="px-2.5 py-1 rounded bg-[#0A66C2]/20 hover:bg-[#0A66C2]/40 text-[#38bdf8] text-[11px] font-semibold shrink-0 flex items-center space-x-1">
              <span>View</span>
              <i data-lucide="external-link" class="w-3 h-3"></i>
            </a>
          </div>
        `).join("");
      }
      showToast(`Retrieved ${data.jobs.length} live jobs from LinkedIn MCP!`);
    } else {
      showToast(data.detail || data.error || "Failed to query LinkedIn MCP", true);
    }
  } catch (err) {
    showToast("LinkedIn MCP query error: " + err.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="search" class="w-3.5 h-3.5"></i><span>Search Live LinkedIn via MCP</span>`;
    }
    lucide.createIcons();
  }
}

function applyLinkedInModalJobsToMainView() {
  if (!lastModalLinkedInJobs || lastModalLinkedInJobs.length === 0) return;
  const existingIds = new Set(appState.jobs.map(j => j.id));
  const newJobs = lastModalLinkedInJobs.filter(j => !existingIds.has(j.id));
  appState.jobs = [...newJobs, ...appState.jobs];
  renderJobCards();
  updateResultsCount();
  if (newJobs.length > 0) selectJob(newJobs[0].id);
  closeLinkedInModal();
  showToast(`Loaded ${newJobs.length} live LinkedIn jobs into main workspace!`);
}

async function recheckLinkedInStatus() {
  try {
    const res = await authFetch("/api/linkedin/status");
    const data = await res.json();
    if (data.authenticated) {
      showToast("LinkedIn MCP session verified & active!");
    } else {
      showToast("LinkedIn session needs sync or li_at cookie.", true);
    }
    checkSystemStatus();
  } catch (err) {
    showToast("Failed to verify LinkedIn status: " + err.message, true);
  }
}

async function saveLinkedInCookieFromModal() {
  const input = document.getElementById("modalLinkedInCookieInput");
  const btn = document.getElementById("modalLinkedInCookieBtn");
  const val = input ? input.value.trim() : "";
  if (!val) {
    showToast("Please enter a valid li_at cookie value", true);
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Saving...</span>`;
    lucide.createIcons();
  }

  try {
    const res = await authFetch("/api/linkedin/connect-cookie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookie: val })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast("LinkedIn session cookie activated successfully!");
      if (input) input.value = "";
      await checkSystemStatus();
    } else {
      showToast(data.detail || data.error || "Failed to activate cookie", true);
    }
  } catch (err) {
    showToast("Error saving cookie: " + err.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="save" class="w-3.5 h-3.5"></i><span>Save & Connect</span>`;
      lucide.createIcons();
    }
  }
}
