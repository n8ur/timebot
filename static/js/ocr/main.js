/* /usr/local/lib/timebot/static/js/ocr/main.js */
/* Copyright 2025 John Ackermann
   Licensed under the MIT License. See LICENSE.TXT for details. */

/*
Copyright 2025 John Ackermann
Licensed under the MIT License. See LICENSE.TXT for details.
*/

document.addEventListener('DOMContentLoaded', function() {
  // Form validation
  const form = document.querySelector('form');
  
  if (form) {
    form.addEventListener('submit', function(event) {
      const title = document.getElementById('title').value.trim();
      const publisher = document.getElementById('publisher').value.trim();
      const source = document.getElementById('source').value.trim();
      const fileInput = document.getElementById('pdf_file');
      
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
      
      // Check file is selected and is PDF
      if (!fileInput.files || fileInput.files.length === 0) {
        errorMessage += 'Please select a PDF file. ';
        isValid = false;
      } else {
        const fileName = fileInput.files[0].name;
        const fileExt = fileName.split('.').pop().toLowerCase();
        
        if (fileExt !== 'pdf') {
          errorMessage += 'Only PDF files are allowed. ';
          isValid = false;
        }
      }
      
      if (!isValid) {
        event.preventDefault();
        alert('Please correct the following errors: ' + errorMessage);
      } else {
        // Show loading indicator
        const submitBtn = document.querySelector('.btn-submit');
        submitBtn.textContent = 'Processing...';
        submitBtn.disabled = true;
      }
    });
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
  toggleSwitch.addEventListener('change', switchTheme, false);
});

