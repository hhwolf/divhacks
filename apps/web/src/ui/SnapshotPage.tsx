import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useEditor } from '../store';
import { RoomScene } from '../scene/Scene';
import { Backdrop } from './Backdrop';
/** Headless render of one layout, no UI, used by the snapshot/thumbnail scripts. */
export function SnapshotPage() {
  const { id } = useParams(); const room = useEditor((s) => s.room); const theme = useEditor((s) => s.theme);
  useEffect(() => { if (id) void useEditor.getState().loadLayout(id); }, [id]);
  return <div className={`editor no-ui theme-${theme}`}><Backdrop />{room && <RoomScene interactive={false} className="canvas" />}</div>;
}
