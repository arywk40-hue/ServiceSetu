'use strict';
let token = '', booking = null, after = 0, lastActive = Date.now(), pending = null;
let generation = 0;
const $ = id => document.getElementById(id);
function notice(text) { $('notice').textContent = text; }
function lock() { generation++; token = ''; booking = null; pending = null; $('token').value = ''; $('text').value = ''; $('workspace').hidden = true; $('login').hidden = false; $('messages').replaceChildren(); $('bookings').replaceChildren(); $('address').textContent = ''; notice('Inbox locked. Enter a valid token to continue.'); }
async function api(path, body) {
  const started = generation;
  lastActive = Date.now();
  const options = {headers: {'Authorization': 'Bearer ' + token}, cache: 'no-store'};
  if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  const response = await fetch(path, options), data = await response.json();
  if (started !== generation) throw new Error('Inbox session changed. Refresh if needed.');
  if (!response.ok) { if (response.status === 401) lock(); throw new Error(data.error || 'Request failed'); }
  return data;
}
async function loadBookings() {
  const data = await api('/api/bookings'); $('bookings').replaceChildren();
  if (booking && !data.bookings.some(item => item.id === booking.id)) { booking = null; $('messages').replaceChildren(); $('address').textContent = ''; $('compose').hidden = true; $('heading').textContent = 'Booking no longer available'; }
  if (!data.bookings.length) $('bookings').textContent = 'No confirmed bookings are assigned to this provider.';
  for (const item of data.bookings) {
    const button = document.createElement('button'); button.className = 'booking';
    button.textContent = item.service + '\n' + new Date(item.slot).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'}) + ' IST\n' + item.id;
    button.onclick = () => openBooking(item).catch(error => notice(error.message)); $('bookings').append(button);
  }
}
async function openBooking(item) {
  booking = item; after = 0; pending = null; $('text').value = ''; $('messages').replaceChildren(); $('heading').textContent = item.service;
  $('address').textContent = item.address ? [item.address.address_line, item.address.area, item.address.city].filter(Boolean).join(', ') : 'Address not provided yet. The customer can add it later.';
  $('compose').hidden = false; await loadMessages();
}
async function loadMessages() {
  if (!booking) return; const id = booking.id;
  const data = await api('/api/bookings/' + encodeURIComponent(id) + '/messages?after=' + after);
  if (!booking || booking.id !== id) return;
  for (const item of data.messages) {
    const article = document.createElement('article'), label = document.createElement('strong'), text = document.createElement('p');
    label.textContent = (item.side === 'customer' ? 'Customer' : 'You') + ' · ' + new Date(item.at * 1000).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'}) + ' IST';
    text.textContent = item.text; article.append(label, text); $('messages').append(article);
  }
  after = data.next_after; $('more').hidden = !data.has_more;
}
$('login').onsubmit = async event => { event.preventDefault(); generation++; token = $('token').value.trim(); $('token').value = ''; try { await loadBookings(); $('login').hidden = true; $('workspace').hidden = false; notice('Authenticated. Refresh to retrieve new bookings and messages.'); } catch (error) { lock(); notice(error.message); } };
$('refresh').onclick = () => loadBookings().then(loadMessages).catch(error => { $('address').textContent = ''; $('messages').replaceChildren(); notice(error.message); });
$('logout').onclick = lock; $('more').onclick = () => loadMessages().catch(error => notice(error.message));
$('compose').onsubmit = async event => { event.preventDefault(); if (!booking) return; const text = $('text').value.trim(); if (!text) return;
  if (!pending || pending.text !== text || pending.booking !== booking.id) pending = {text, client_id: crypto.randomUUID(), booking: booking.id};
  try { await api('/api/bookings/' + encodeURIComponent(booking.id) + '/messages', {text: pending.text, client_id: pending.client_id}); pending = null; $('text').value = ''; await loadMessages(); notice('Saved. Customer notification is queued; delivery depends on the mesh connection.'); } catch (error) { notice(error.message); }
};
setInterval(() => { if (token && Date.now() - lastActive > 5 * 60 * 1000) lock(); }, 10000);
