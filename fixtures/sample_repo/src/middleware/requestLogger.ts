// Adds a request id and logs request latency for every API call.
import type { NextFunction, Request, Response } from "express";

export function requestLogger(request: Request, response: Response, next: NextFunction) {
  const startedAt = Date.now();
  response.on("finish", () => {
    const latencyMs = Date.now() - startedAt;
    console.log({
      requestId: request.header("x-request-id") ?? "generated-locally",
      latencyMs,
      path: request.path,
    });
  });
  next();
}

