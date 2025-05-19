document.addEventListener('DOMContentLoaded', function() {
  // Auto-refresh queue page every 10 seconds if there are processing documents
  if (document.querySelector('.queue-table') && 
      document.querySelector('.status-badge.status-processing')) {
    setTimeout(function() {
      window.location.reload();
    }, 10000);
  }
  
  // Auto-hide flash messages after 5 seconds
  const flashMessages = document.querySelectorAll('.alert');
  if (flashMessages.length > 0) {
    setTimeout(function() {
      flashMessages.forEach(function(message) {
        message.style.opacity = '0';
        message.style.transition = 'opacity 0.5s';
        setTimeout(function() {
          message.style.display = 'none';
        }, 500);
      });
    }, 5000);
  }
  
  // Theme switcher
  const toggleSwitch = document.querySelector('.theme-switch input[type="checkbox"]');
  const themeLabel = document.querySelector('.theme-label');
  
  // Check for saved theme preference
  const currentTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', currentTheme);
  
  // Update checkbox state based on current theme
  if (currentTheme === 'dark') {
    toggleSwitch.checked = true;
    themeLabel.textContent = 'Light Mode';
  }
  
  // Switch theme function
  function switchTheme(e) {
    if (e.target.checked) {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('theme', 'dark');
      themeLabel.textContent = 'Light Mode';
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem('theme', 'light');
      themeLabel.textContent = 'Dark Mode';
    }
  }
  
  // Add event listener for theme switch
  if (toggleSwitch) {
    toggleSwitch.addEventListener('change', switchTheme, false);
  }
  
  // Form validation for directory input
  const directoryForm = document.querySelector('form[action*="scan-directory"]');
  if (directoryForm) {
    directoryForm.addEventListener('submit', function(event) {
      const directoryPath = document.getElementById('directory_path').value.trim();
      
      if (!directoryPath) {
        event.preventDefault();
        alert('Please enter a directory path');
      }
    });
  }
  
  // Form validation for metadata
  const metadataForm = document.querySelector('form[action*="finalize"]');
  if (metadataForm) {
    metadataForm.addEventListener('submit', function(event) {
      const title = document.getElementById('title').value.trim();
      const publisher = document.getElementById('publisher').value.trim();
      const source = document.getElementById('source').value.trim();
      
      let isValid = true;
      let errorMessage = '';
      
      // Check required fields
      if (!title) {
        errorMessage += 'Title is required. ';
        isValid = false;
      }
      
      if (!publisher) {
        errorMessage += 'Publisher is required. ';
        isValid = false;
      }
      
      if (!source) {
        errorMessage += 'Source is required. ';
        isValid = false;
      }
      
      if (!isValid) {
        event.preventDefault();
        alert('Please correct the following errors: ' + errorMessage);
      } else {
        // Show loading indicator
        const submitBtn = document.querySelector('.btn-primary');
        submitBtn.textContent = 'Processing...';
        submitBtn.disabled = true;
      }
    });
  }
});

