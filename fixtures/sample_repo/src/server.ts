// Bootstraps the HTTP server and attaches request logging middleware.
import express from "express";

import { requestLogger } from "./middleware/requestLogger";
import { questionsRouter } from "./routes/questions";

const app = express();

app.use(express.json());
app.use(requestLogger);
app.use("/questions", questionsRouter);

app.listen(3000, () => {
  console.log("Atlas Tasks listening on port 3000");
});

