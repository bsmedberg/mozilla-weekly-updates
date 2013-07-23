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
