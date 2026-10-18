---
permalink: /
title: "*To make the unknown known.*"
author_profile: true
redirect_from: 
  - /about/
  - /about.html
---

<br>

<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 1.1em; line-height: 1.8; color: #333;">

<p>
  Thank you for visiting! I’m currently in the process of updating and adding content to this page. Please check back soon for more updates. Sorry for any inconvenience, and feel free to reach out if you need any information! You can contact me at <a href="mailto:cw.wu1103@gmail.com" style="text-decoration: underline; color: #0066cc;">cw.wu1103@gmail.com</a>.
</p>

<h2 style="margin-top: 40px; margin-bottom: 20px; font-weight: 600; border-bottom: 1px solid #eaeaea; padding-bottom: 10px;">About me</h2>

<p>
  My current research focuses on the <strong>high-order organization</strong> of human brain networks, aiming to uncover complex neural dynamics in both healthy and diseased brains.
</p>

<p>
  In 2025, I received my Master’s degree from the <em>South China Normal University</em>, under the supervision of Prof. Dr. <a href="https://scholar.google.com/citations?user=4_djMV0AAAAJ&hl=en&oi=ao" target="_blank" style="color: #0066cc;">Jinhui Wang</a>. 
</p>

<p>
  Currently, I am a Ph.D. student at the <em>University of Electronic Science and Technology of China</em>, supervised by Prof. Dr. <a href="https://scholar.google.com/citations?user=s8DIQOwAAAAJ" target="_blank" style="color: #0066cc;">Xujun Duan</a>.
</p>




<section id="contact" style="margin-top: 48px; padding: 24px; border: 1px solid #e3e7eb; border-radius: 10px; background: #fafbfc;">
  <h2 style="margin: 0 0 8px; font-size: 1.3em; font-weight: 600;">Contact me</h2>
  <p style="margin: 0 0 20px;">Have a question or want to collaborate? Write me a message.</p>
  <form id="home-contact-form">
    <label for="contact-subject" style="display: block; margin-bottom: 6px; font-weight: 600;">Subject</label>
    <input id="contact-subject" name="subject" type="text" required style="display: block; width: 100%; box-sizing: border-box; margin-bottom: 16px; padding: 10px 12px; border: 1px solid #cbd5df; border-radius: 6px; font: inherit;" />

    <label for="contact-message" style="display: block; margin-bottom: 6px; font-weight: 600;">Message</label>
    <textarea id="contact-message" name="message" rows="6" required style="display: block; width: 100%; box-sizing: border-box; margin-bottom: 16px; padding: 10px 12px; border: 1px solid #cbd5df; border-radius: 6px; font: inherit; resize: vertical;"></textarea>

    <button type="submit" style="padding: 10px 18px; border: 0; border-radius: 6px; background: #267ca3; color: #fff; font: inherit; font-weight: 600; cursor: pointer;">Send email</button>
  </form>
  <p style="margin: 16px 0 0; font-size: 0.85em; color: #606b73;">This opens your email app with the message ready to send. You can also write directly to <a href="mailto:{{ site.author.email | escape }}">{{ site.author.email | escape }}</a>.</p>
</section>

<script>
(function () {
  var form = document.getElementById("home-contact-form");
  if (!form) return;
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var subject = form.elements.subject.value.trim();
    var message = form.elements.message.value.trim();
    if (!subject || !message) return;
    var recipient = {{ site.author.email | jsonify }};
    window.location.href = "mailto:" + recipient
      + "?subject=" + encodeURIComponent(subject)
      + "&body=" + encodeURIComponent(message);
  });
})();
</script>

</div>
