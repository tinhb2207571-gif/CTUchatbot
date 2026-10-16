// Một dòng JSON có thể bị chia ở bất kỳ byte nào khi đi qua mạng.
export async function* readChatStream(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let pending = ""
  let finished = false
  try {
    while (!finished) {
      const { done, value } = await reader.read()
      finished = done
      pending += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const lines = pending.split("\n")
      pending = lines.pop() ?? ""
      if (done && pending) {
        lines.push(pending)
        pending = ""
      }
      for (const line of lines) {
        if (line.startsWith("3:")) throw new Error(JSON.parse(line.slice(2)))
        if (line.startsWith("0:")) {
          const text: unknown = JSON.parse(line.slice(2))
          if (typeof text !== "string") throw new Error("Dữ liệu trả lời không hợp lệ.")
          yield text
        }
      }
    }
  } finally {
    if (!finished) await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
