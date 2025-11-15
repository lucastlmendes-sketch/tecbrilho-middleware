// erikaParser.js
function splitErikaResponse(fullText) {
  const startTag = "### ERIKA_ACTION";
  const endTag = "### END_ERIKA_ACTION";

  const startIndex = fullText.indexOf(startTag);
  const endIndex = fullText.indexOf(endTag);

  if (startIndex === -1 || endIndex === -1) {
    return {
      clientText: fullText.trim(),
      action: null
    };
  }

  const clientText = fullText.slice(0, startIndex).trim();
  const jsonPart = fullText
    .slice(startIndex + startTag.length, endIndex)
    .trim();

  let action = null;
  try {
    action = JSON.parse(jsonPart);
  } catch (e) {
    console.error("Falha ao parsear ERIKA_ACTION:", e);
  }

  return { clientText, action };
}

module.exports = { splitErikaResponse };
