// Exposes the /questions endpoint that accepts user repo questions.
import { Router } from "express";

export const questionsRouter = Router();

questionsRouter.post("/", (_request, response) => {
  response.json({ ok: true });
});

