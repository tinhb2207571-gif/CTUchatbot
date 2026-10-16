import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../lib/chat-stream.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } })
const { readChatStream } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

function bytesStream(text) {
  const bytes = new TextEncoder().encode(text)
  return new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  })
}

test('preserves Vietnamese when every UTF-8 byte arrives separately', async () => {
  const parts = []
  for await (const text of readChatStream(bytesStream('0:"Xin "\n0:"chào Đại học Cần Thơ"\n'))) parts.push(text)
  assert.equal(parts.join(''), 'Xin chào Đại học Cần Thơ')
})

test('reads final frame without newline', async () => {
  const parts = []
  for await (const text of readChatStream(bytesStream('0:"cuối"'))) parts.push(text)
  assert.deepEqual(parts, ['cuối'])
})

test('surfaces server errors after preserving partial answer', async () => {
  const reader = readChatStream(bytesStream('0:"partial"\n3:"Lỗi kết nối"\n'))
  assert.equal((await reader.next()).value, 'partial')
  await assert.rejects(reader.next(), /Lỗi kết nối/)
})

test('cancels network reader when consumer stops early', async () => {
  let cancelled = false
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('0:"first"\n')) },
    cancel() { cancelled = true },
  })
  const reader = readChatStream(stream)
  await reader.next()
  await reader.return()
  assert.equal(cancelled, true)
})
