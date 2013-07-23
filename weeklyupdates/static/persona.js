navigator.id.watch({
  loggedInUser: gUsername,
  onlogin: function(assertion) {
    document.getElementById('loginAssertion').value = assertion;
    document.getElementById('login').submit();
  },
  onlogout: function() {
    document.getElementById('loginAssertion').value = "";
    document.getElementById('login').submit();
  }
});

function doLogin()
{
  navigator.id.request();
}

function doLogout()
{
  navigator.id.logout();
}

function extractPreview()
{
  var f = document.getElementById('previewFrame');
  var pdoc = f.contentDocument;
  var pdiv = pdoc.querySelector('.postdetail');
  if (!pdiv) {
    return;
  }
  var pinner = document.getElementById('previewInner');
  pinner.innerHTML = '';
  pinner.appendChild(pdiv);
  document.getElementById('previewOuter').classList.remove('hidden');
}
document.getElementById('previewFrame').addEventListener('load', extractPreview, false);

function doPreview()
{
  var form = document.getElementById('postform');
  var oldAction = form.action;
  form.action = kPreviewURL;
  form.target = "previewFrame";
  form.submit();
}

function clearPreview()
{
  document.getElementById('previewOuter').classList.add('hidden');
}
