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
  form.action = oldAction;
  form.target = "_self";
}

function clearPreview()
{
  document.getElementById('previewOuter').classList.add('hidden');
}

function doHide()
{
  var hide = $('#hide_button');
  if (hide.attr('value') === 'Hide') {
    hide.attr('value', 'Show');
  } else {
    hide.attr('value', 'Hide');
  }
  $('.bugheader').fadeToggle();
  $('.bugs').slideToggle();
}

function doUpdateBugStatus(event)
{
  var target = $(event.target);
  var button = target.closest('.dropdown').children('button');
  var bug = button.attr('id');
  var bugStatus = target.attr('status');
  var select = $('select[name="' + bug + '"]');
  var option = select.children('option[value="' + bugStatus + '"]');

  button.empty()
    .append(target.contents().clone())
    .append('<span class="caret"></span>');

  select.children('option').removeAttr('selected');
  option.attr('selected', '');
}

