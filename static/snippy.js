$(document).ready(function() {
  $(".snippy-embed-link").each(function(){
    var a= $(this),b=a.next(".snippy-embed-box");
    function c() {
      a.toggle();
      b.toggle();
      b.is(":visible")&&b.get(0).select();
      return false
    }
    a.click(c);b.blur(c)
  });

  function show_confirm() {
    var r=confirm("Are you sure?");
    if (r==true){
      return true;
    } else {
      return false;
    }
  }
});

