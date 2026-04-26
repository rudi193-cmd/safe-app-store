// safe-app-manifest.js — r/LLMPhysics Competition Judge
export const manifest = {
  id: "safe-app-llmphysics",
  name: "r/LLMPhysics Judge",
  description: "Community paper competition scoring tool for r/LLMPhysics",
  version: "0.1.0",
  author: "AllHailSeizure",
  ring: "bridge",
  scopes: ["llm:call"],
  dataPolicy: {
    storageLocation: "client",
    serverSide: "none",
    dataRetention: "session"
  },
  entry: "site/index.html"
};
