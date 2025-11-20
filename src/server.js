// src/server.js

require("dotenv").config();
const express = require("express");
const bodyParser = require("body-parser");
const cors = require("cors");

const app = express();

// Configuração básica
app.use(cors());
app.use(bodyParser.json());

// Rota principal: Render usa isso como health-check
app.get("/", (req, res) => {
  res.json({ status: "ok", service: "tecbrilho-middleware" });
});

// Rota que usaremos para o Kommo (ainda vazia)
app.post("/kommo/webhook", (req, res) => {
  res.json({ status: "received" });
});

// Render define a porta automaticamente
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(`Servidor rodando na porta ${PORT}`);
});
