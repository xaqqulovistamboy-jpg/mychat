(function () {
  if (window.__chatNotifyLoaded) return;
  window.__chatNotifyLoaded = true;

  var baseTitle = document.title.replace(/^\(\d+\)\s*/, '');
  var unread = 0;
  var retries = 0;

  // Banner uchun uslublar (alohida CSS fayl kerak emas)
  var style = document.createElement('style');
  style.textContent =
    '.chat-notify-toast{position:fixed;top:12px;left:50%;transform:translate(-50%,-150%);' +
    'width:min(92vw,380px);background:#17212b;color:#f5f5f5;border-radius:14px;padding:10px 14px;' +
    'box-shadow:0 6px 20px rgba(0,0,0,.35);cursor:pointer;z-index:9999;' +
    'transition:transform .3s ease;font-family:-apple-system,Segoe UI,Roboto,sans-serif}' +
    '.chat-notify-toast.show{transform:translate(-50%,0)}' +
    '.chat-notify-toast .cn-title{font-weight:600;font-size:14px;color:#6ab3f3;margin-bottom:2px}' +
    '.chat-notify-toast .cn-body{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}';
  document.head.appendChild(style);

  function currentChat() {
    return window.CURRENT_CHAT || null;
  }

  function chatUrl(chat) {
    if (chat === 'general') return '/chat/general/';
    return '/chat/u/' + encodeURIComponent(chat.slice(2)) + '/';
  }

  function setTitle() {
    document.title = (unread > 0 ? '(' + unread + ') ' : '') + baseTitle;
  }

  // Qisqa "ding" ovozi — fayl kerak emas
  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = window.__audioCtx || (window.__audioCtx = new Ctx());
      if (ctx.state === 'suspended') ctx.resume();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.27);
    } catch (e) {}
  }

  function showBanner(sender, text, chat) {
    var t = document.createElement('div');
    t.className = 'chat-notify-toast';

    var who = document.createElement('div');
    who.className = 'cn-title';
    who.textContent = sender;

    var body = document.createElement('div');
    body.className = 'cn-body';
    body.textContent = text;

    t.appendChild(who);
    t.appendChild(body);
    t.addEventListener('click', function () {
      location.href = chatUrl(chat);
    });
    document.body.appendChild(t);

    requestAnimationFrame(function () { t.classList.add('show'); });
    setTimeout(function () {
      t.classList.remove('show');
      setTimeout(function () { t.remove(); }, 300);
    }, 4000);
  }

  function systemNotify(sender, text, chat) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    try {
      var n = new Notification(sender, { body: text, tag: chat });
      n.onclick = function () {
        window.focus();
        location.href = chatUrl(chat);
        n.close();
      };
    } catch (e) {}
  }
    function markRead(chat) {
    var meta = document.querySelector('meta[name="csrf-token"]');
    fetch('/chat/read/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': meta ? meta.content : '' },
      body: JSON.stringify({ chat: chat })
    }).catch(function () {});
  }

  function bumpBadge(chat) {
    var row = document.querySelector('[data-chat="' + chat + '"]');
    if (!row) return;
    var badge = row.querySelector('.badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'badge';
      row.querySelector('.right').appendChild(badge);
    }
    badge.textContent = String((parseInt(badge.textContent, 10) || 0) + 1);
  }
  function onMessage(data) {
    var chat = data.chat;
    var inView = document.visibilityState === 'visible' && chat === currentChat();
        if (inView) {
      markRead(chat);   // ochiq suhbatda — darhol o'qilgan deb belgilaymiz
      return;
    }
    bumpBadge(chat);    // boshqa suhbatda — chatlar ro'yxatidagi hisobni oshiramiz // Shu suhbatda ekranda turibmiz — bildirishnoma kerak emas

    unread += 1;
    setTitle();
    beep();
    try { navigator.vibrate && navigator.vibrate(120); } catch (e) {}
    showBanner(data.sender, data.text, chat);
    systemNotify(data.sender, data.text, chat);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      unread = 0;
      setTitle();
    }
  });

  // Birinchi bosishda brauzer bildirishnoma ruxsatini so'raydi
  document.addEventListener('click', function askPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, { once: true });

  function connect() {
    var scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    var ws = new WebSocket(scheme + '://' + location.host + '/ws/notify/');

    ws.onopen = function () { retries = 0; };

    ws.onmessage = function (e) {
      var data;
      try { data = JSON.parse(e.data); } catch (err) { return; }
      onMessage(data);
    };

    ws.onclose = function () {
      if (retries >= 20) return;
      var delay = Math.min(15000, 1000 * Math.pow(2, retries));
      retries += 1;
      setTimeout(connect, delay);
    };
  }

  connect();
})();