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
 * - Also stores the last playback time of the track
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

    const savedTime = parseFloat(localStorage.getItem("lastTime:" + folderKey));

    // Wait until metadata is loaded before seeking
    player.onloadedmetadata = () => {
      if (!isNaN(savedTime)) {
        player.currentTime = savedTime;
      }

      // Try to autoplay, fallback silently if blocked
      player.play().catch(err => {
        // If autoplay is blocked, just log the error. It's usually harmless
        if (err.name !== "AbortError" && err.name !== "NotAllowedError") {
          console.error("Playback failed:", err);
        }
      });
    };

    player.load();
  }

  // On click: find parent <li> and play its track
  window.playFromList = function (trackElement) {
    const li = trackElement.closest("li");
    index = playlistItems.indexOf(li);
    localStorage.removeItem("lastTime:" + folderKey); // Clear old time
    loadAndPlay(index);
  }

  // Advance to next track when one ends
  function playNext() {
    // Clear saved time when moving to next track
    localStorage.removeItem("lastTime:" + folderKey);

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

  // Periodically store current playback time in localStorage (every 5 seconds)
  let lastTimeSave = 0;
  player.addEventListener("timeupdate", () => {
    const now = Date.now();
    if (now - lastTimeSave > 5000) {
      localStorage.setItem("lastTime:" + folderKey, player.currentTime);
      lastTimeSave = now;
    }
  });

  // Initial load: play the last remembered track
  loadAndPlay(index);
});
