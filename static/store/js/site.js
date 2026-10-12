document.addEventListener("DOMContentLoaded", function () {
  var menuButton = document.querySelector("[data-menu-toggle]");
  var navigation = document.querySelector("[data-navigation]");
  if (menuButton && navigation) {
    menuButton.addEventListener("click", function () {
      var isOpen = navigation.classList.toggle("is-open");
      menuButton.setAttribute("aria-expanded", String(isOpen));
      document.body.classList.toggle("menu-open", isOpen);
    });
  }

  document.querySelectorAll(".message").forEach(function (message) {
    window.setTimeout(function () {
      message.classList.add("message-fade");
    }, 5500);
  });
});
