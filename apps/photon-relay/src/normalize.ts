import type { NormalizedAttachment, NormalizedPhotonMessage } from './types.js';

type AnyRecord = Record<string, unknown>;

function asRecord(value: unknown): AnyRecord {
  return value && typeof value === 'object' ? value as AnyRecord : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

function contentText(content: unknown): string {
  if (typeof content === 'string') return content;
  const c = asRecord(content);
  return asString(c.text) ?? asString(c.value) ?? '';
}

async function readAttachmentData(value: unknown): Promise<string | undefined> {
  const v = asRecord(value);
  const read = v.read ?? v.arrayBuffer ?? v.bytes;
  if (typeof read !== 'function') return undefined;
  const bytes = await read.call(value);
  if (bytes instanceof ArrayBuffer) return Buffer.from(bytes).toString('base64');
  if (ArrayBuffer.isView(bytes)) return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString('base64');
  return undefined;
}

async function normalizeAttachment(value: unknown): Promise<NormalizedAttachment | null> {
  const v = asRecord(value);
  const content = asRecord(v.content);
  const url = asString(v.url) ?? asString(content.url);
  const mimeType = asString(v.mimeType) ?? asString(v.mime_type) ?? asString(v.mediaType) ?? asString(content.mimeType);
  const fileName = asString(v.fileName) ?? asString(v.name) ?? asString(content.name);
  const dataBase64 = asString(v.dataBase64) ?? asString(content.dataBase64) ?? await readAttachmentData(value);
  if (!url && !dataBase64) return null;
  return { ...(url ? { url } : {}), ...(mimeType ? { mimeType } : {}), ...(fileName ? { fileName } : {}), ...(dataBase64 ? { dataBase64 } : {}) };
}

async function collectAttachments(message: AnyRecord): Promise<NormalizedAttachment[]> {
  const candidates: unknown[] = [];
  if (Array.isArray(message.attachments)) candidates.push(...message.attachments);
  const content = message.content;
  if (Array.isArray(content)) candidates.push(...content.filter((c) => asRecord(c).type === 'attachment' || asRecord(c).mimeType));
  else if (asRecord(content).type === 'attachment') candidates.push(content);
  const normalized = await Promise.all(candidates.map((c) => normalizeAttachment(c)));
  return normalized.filter((a): a is NormalizedAttachment => Boolean(a));
}

export async function normalizeSpectrumMessage(message: unknown): Promise<NormalizedPhotonMessage> {
  const m = asRecord(message);
  const sender = asRecord(m.sender);
  const user = asRecord(m.user);
  const id = asString(m.id) ?? asString(m.guid) ?? asString(m.messageId);
  const senderId = asString(sender.id) ?? asString(sender.phone) ?? asString(user.id) ?? asString(user.phone) ?? asString(m.from);
  if (!id) throw new Error('Photon message is missing id');
  if (!senderId) throw new Error('Photon message is missing sender');
  const text = asString(m.text) ?? contentText(m.content);
  return { messageId: id, sender: senderId, text, attachments: await collectAttachments(m) };
}

export function composeReply(response: { reply: string; links?: string[] }): string {
  return [response.reply, ...(response.links ?? [])].filter(Boolean).join('\n');
}
