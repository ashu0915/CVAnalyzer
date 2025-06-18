const API_URL = 'http://127.0.0.1:5000/api';
let currentUser = null;
let currentCvId = null;
let currentResultId = null;

const sections = {
    home: document.getElementById('home-section'),
    upload: document.getElementById('upload-section'),
    analyze: document.getElementById('analyze-section'),
    results: document.getElementById('results-section'),
    history: document.getElementById('history-section'),
    login: document.getElementById('login-section')
};

document.getElementById('nav-home').addEventListener('click', () => showSection('home'));
document.getElementById('nav-upload').addEventListener('click', () => showSection('upload'));
document.getElementById('nav-analyze').addEventListener('click', () => showSection('analyze'));
document.getElementById('nav-history').addEventListener('click', () => {
    loadAnalysisHistory();
    showSection('history');
});
document.getElementById('login-btn').addEventListener('click', () => showSection('login'));
document.getElementById('get-started-btn').addEventListener('click', () => showSection('upload'));
document.getElementById('go-to-analyze-btn').addEventListener('click', () => {
    loadUserCvs();
    showSection('analyze');
});

function showSection(sectionName) {
    Object.keys(sections).forEach(key => {
        sections[key].classList.add('hidden');
    });
    sections[sectionName].classList.remove('hidden');
}

// Tab handling
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        // Get the parent tab container
        const tabContainer = button.closest('.tab-container');
        
        // Remove active class from all buttons and content in this container
        tabContainer.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        tabContainer.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        // Add active class to clicked button
        button.classList.add('active');
        
        // Show corresponding content
        const tabId = button.getAttribute('data-tab');
        const contentId = tabId.includes('form') ? `${tabId}-tab` : `${tabId}-tab`;
        document.getElementById(contentId).classList.add('active');
    });
});

// Load user's CVs for the analyze section
async function loadUserCvs() {
    try {
        const userId = currentUser ? currentUser.id : 0;
        const response = await fetch(`${API_URL}/user-cvs?user_id=${userId}`);
        const data = await response.json();
        
        if (data.success) {
            console.log(data.cvs[0]);
            console.log("Data");
            const cvSelect = document.getElementById('cv-select');
            cvSelect.innerHTML = '<option value="">-- Select your CV --</option>';
            
            data.cvs.forEach(cv => {
                const option = document.createElement('option');
                option.value = cv.id;
                option.textContent = cv.file_name;
                console.log(cv.file_name);
                cvSelect.appendChild(option);
            });
        } else {
            console.error('Failed to load CVs:', data.error);
        }
    } catch (error) {
        console.error('Error loading CVs:', error);
    }
}

// Load analysis history
async function loadAnalysisHistory() {
    try {
        const userId = currentUser ? currentUser.id : 0;
        console.log(`analysis: ${userId}`);
        const response = await fetch(`${API_URL}/analysis-history?user_id=${userId}`);
        const data = await response.json();
        
        if (data.success) {
            const historyList = document.getElementById('history-list');
            historyList.innerHTML = '';
            
            if (data.history.length === 0) {
                historyList.innerHTML = '<p>No analysis history found.</p>';
                return;
            }
            
            data.history.forEach(item => {
                const historyItem = document.createElement('div');
                historyItem.className = 'result-card';
                historyItem.innerHTML = `
                    <h3>${item.job_title}</h3>
                    <p>CV: ${item.cv_name}</p>
                    <p>Score: ${item.score}%</p>
                    <p>Date: ${new Date(item.created_at).toLocaleString()}</p>
                    <button class="view-result-btn" data-id="${item.id}">View Result</button>
                `;
                historyList.appendChild(historyItem);
            });
            
            document.querySelectorAll('.view-result-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const resultId = btn.getAttribute('data-id');
                    await loadAnalysisResult(resultId);
                    showSection('results');
                });
            });
        } else {
            console.error('Failed to load history:', data.error);
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Load a specific analysis result
async function loadAnalysisResult(resultId) {
    try {
        const response = await fetch(`${API_URL}/analysis-result/${resultId}`);
        const data = await response.json();
        
        if (data.success) {
            const result = data.result;
            currentResultId = result.id;
            
            // Display the result
            document.getElementById('match-score').textContent = result.score;
            document.getElementById('feedback-content').innerHTML = result.feedback;
            
            const suggestionsList = document.getElementById('suggestions-list');
            suggestionsList.innerHTML = '';
            result.suggestions.forEach(suggestion => {
                const li = document.createElement('li');
                li.textContent = suggestion;
                suggestionsList.appendChild(li);
            });
            
            document.getElementById('improved-cv-content').innerHTML = result.improved_cv.replace(/\n/g, '<br>');
        } else {
            console.error('Failed to load result:', data.error);
        }
    } catch (error) {
        console.error('Error loading result:', error);
    }
}


document.getElementById('nav-analyze').addEventListener('click', async() => {
    await loadUserCvs();
});

// CV Upload Form
document.getElementById('cv-upload-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const fileInput = document.getElementById('cv-file');
  if (!fileInput.files.length) {
    alert('Please select a file to upload');
    return;
  }

  const formData = new FormData();
  formData.append('cv', fileInput.files[0]);
  formData.append('user_id', currentUser ? currentUser.id : 0);

  console.log(`user_id ${currentUser?.id}`);
  
  const uploadBtn = e.target.querySelector('button[type="submit"]');
  uploadBtn.textContent = 'Uploading...';
  uploadBtn.disabled = true;

  try {
    console.log("Hi");

    const response = await fetch(`${API_URL}/upload-cv`, {
      method: 'POST',
      body: formData
    });

    const rawText = await response.text();
    console.log("Raw response text:", rawText);

    let data;
    try {
      data = JSON.parse(rawText);
    } catch (jsonError) {
      console.error("❌ Failed to parse JSON from server:", jsonError);
      throw new Error("Server returned invalid JSON.");
    }

    uploadBtn.textContent = 'Upload';
    uploadBtn.disabled = false;

    if (data.success) {
      currentCvId = data.cv_id;
      document.getElementById('upload-result').classList.remove('hidden');
      document.getElementById('cv-upload-form').classList.add('hidden');
      alert("✅ CV uploaded successfully");
    } else {
      console.error("Server error:", data);
      alert(`Upload failed: ${data.error || 'Unknown server error'}`);
    }

  } catch (error) {
    console.error('Error uploading CV:', error);
    alert(`❌ Upload failed. ${error.message || error}`);
    uploadBtn.textContent = 'Upload';
    uploadBtn.disabled = false;
  }
});

// Analyze Button
document.getElementById('analyze-btn').addEventListener('click', async () => {
    const cvId = document.getElementById('cv-select').value;
    const jobDescription = document.getElementById('job-description').value;
    
    if (!cvId) {
        alert('Please select a CV');
        return;
    }
    
    if (!jobDescription.trim()) {
        alert('Please enter a job description');
        return;
    }
    
    try {
        document.getElementById('analysis-loading').classList.remove('hidden');
        
        // First save the job description
        const jobResponse = await fetch(`${API_URL}/job-description`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                title: 'Job Posting ' + new Date().toLocaleDateString(),
                content: jobDescription,
                user_id: currentUser ? currentUser.id : 0
            })
        });
        
        const jobData = await jobResponse.json();
        
        if (jobData.success) {
            const jobDescriptionId = jobData.job_description_id;
            
            // Now analyze the CV against the job description
            const analyzeResponse = await fetch(`${API_URL}/analyze`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cv_id: cvId,
                    job_description_id: jobDescriptionId,
                    user_id: currentUser ? currentUser.id : 0
                })
            });
            
            const analyzeData = await analyzeResponse.json();
            
            document.getElementById('analysis-loading').classList.add('hidden');
            
            if (analyzeData.success) {
                // Display the analysis result
                currentResultId = analyzeData.result_id;
                const result = analyzeData.analysis;
                
                document.getElementById('match-score').textContent = result.score;
                document.getElementById('feedback-content').innerHTML = result.feedback;
                
                const suggestionsList = document.getElementById('suggestions-list');
                suggestionsList.innerHTML = '';
                result.suggestions.forEach(suggestion => {
                    const li = document.createElement('li');
                    li.textContent = suggestion;
                    suggestionsList.appendChild(li);
                });
                
                document.getElementById('improved-cv-content').innerHTML = result.improved_cv.replace(/\n/g, '<br>');
                
                showSection('results');
            } else {
                alert(`Analysis failed: ${analyzeData.error}`);
            }
        } else {
            document.getElementById('analysis-loading').classList.add('hidden');
            alert(`Failed to save job description: ${jobData.error}`);
        }
    } catch (error) {
        document.getElementById('analysis-loading').classList.add('hidden');
        console.error('Error analyzing CV:', error);
        alert('Analysis failed. Please try again later.');
    }
});

// Download Improved CV Button
document.getElementById('download-cv-btn').addEventListener('click', async () => {
    if (!currentResultId) {
        alert('No analysis result available');
        return;
    }
    
    try {
        window.location.href = `${API_URL}/export-cv/${currentResultId}?format=txt`;
    } catch (error) {
        console.error('Error downloading CV:', error);
        alert('Download failed. Please try again later.');
    }
});

// Login Form
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    try {
        const response = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentUser = {
                id: data.user_id,
                email: data.email
            };
            console.log(`Login: ${currentUser.id} , ${currentUser.email}`);
            document.getElementById('login-btn').textContent = 'Logout';
            showSection('home');
        } else {
            alert(`Login failed: ${data.error}`);
        }
    } catch (error) {
        console.error('Error logging in:', error);
        alert('Login failed. Please try again later.');
    }
});

// Register Form
document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-confirm-password').value;
    
    if (password !== confirmPassword) {
        alert('Passwords do not match');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentUser = {
                id: data.user_id,
                email: data.email
            };
            document.getElementById('login-btn').textContent = 'Logout';
            showSection('home');
        } else {
            alert(`Registration failed: ${data.error}`);
        }
    } catch (error) {
        console.error('Error registering:', error);
        alert('Registration failed. Please try again later.');
    }
});

// Logout functionality
document.getElementById('login-btn').addEventListener('click', () => {
    if (currentUser) {
        currentUser = null;
        document.getElementById('login-btn').textContent = 'Login';
    }
    showSection('login');
});