export interface NormalizedAttachment {
  url?: string;
  mimeType?: string;
  fileName?: string;
  dataBase64?: string;
}

export interface NormalizedPhotonMessage {
  messageId: string;
  sender: string;
  text: string;
  attachments: NormalizedAttachment[];
}

export interface BackendResponse {
  ok: boolean;
  reply: string;
  links?: string[];
  reviewLink?: string;
  generateLink?: string;
  itemId?: string | null;
  layoutId?: string | null;
}
