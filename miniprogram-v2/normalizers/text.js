"use strict";

/**
 * The mini-program renders assistant content with <text>, not a Markdown
 * renderer. Keep the display contract plain-text so model formatting tokens
 * never leak into the UI.
 */
function cleanText(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/\*\*([\s\S]*?)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

module.exports = { cleanText };
