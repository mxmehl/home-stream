// SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
//
// SPDX-License-Identifier: GPL-3.0-only

function copyToClipboard(text, button) {
  navigator.clipboard.writeText(text).then(() => {
    button.classList.add("secondary");
  });
}

/**
 * Playlist player logic for Home Stream
 *
 * - Remembers the last played track index per folder using localStorage
 * - Updates the "Now Playing" label and highlights the active track
 * - Allows user to click a track name to start playing it
 * - Automatically plays the next track when one finishes
 *
 * Requires:
 * - <body data-slug-path="..."> to identify the current folder
 * - #media-player element (audio or video)
 * - #playlist <ul> with <li><span class="track">Track Name</span></li> items
 * - #now-playing span to display currently playing track
 */
document.addEventListener("DOMContentLoaded", function () {
  // Get DOM elements
  const player = document.getElementById("media-player");
  const playlistItems = [...document.querySelectorAll("#playlist li")];
  const nowPlaying = document.getElementById("now-playing");
  const folderKey = document.body.dataset.slugPath;

  // Exit silently if this isn't a playlist view
  if (!player || playlistItems.length === 0 || !nowPlaying || !folderKey) return;

  // Load last played index from localStorage, fallback to 0
  let index = parseInt(localStorage.getItem("lastPlayed:" + folderKey)) || 0;

  // Highlight the current track and update label
  function setActive(i) {
    playlistItems.forEach((item, j) => {
      item.classList.toggle("active", j === i);
    });
    nowPlaying.textContent = playlistItems[i].textContent;
    // Store the last played index for this folder in localStorage
    localStorage.setItem("lastPlayed:" + folderKey, i);
  }

  // Play track by index and set active state
  function loadAndPlay(i) {
    const src = playlistItems[i].dataset.src;
    player.src = src;
    setActive(i);
    player.load();
    player.play().catch(err => {
      // Suppress harmless abort errors
      if (err.name !== "AbortError" && err.name !== "NotAllowedError") {
        console.error("Playback failed:", err);
      }
    });
  }

  // On click: find parent <li> and play its track
  window.playFromList = function (trackElement) {
    const li = trackElement.closest("li");
    index = playlistItems.indexOf(li);
    loadAndPlay(index);
  }

  // Advance to next track when one ends
  function playNext() {
    if (index + 1 < playlistItems.length) {
      index++;
      loadAndPlay(index);
    }
  }

  // Attach click listeners to each track name
  playlistItems.forEach(item => {
    const track = item.querySelector(".track");
    if (track) track.addEventListener("click", () => playFromList(track));
  });

  // Attach "ended" event to play next track automatically
  player.addEventListener("ended", playNext);

  // Initial load: play the last remembered track
  loadAndPlay(index);
});
