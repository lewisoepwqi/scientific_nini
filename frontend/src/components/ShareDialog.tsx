import React, { useState } from 'react';
import { shareApi } from '@services/shareApi';

interface ShareDialogProps {
  taskId: string;
}

export const ShareDialog: React.FC<ShareDialogProps> = ({ taskId }) => {
  const [memberId, setMemberId] = useState('');
  const [permission, setPermission] = useState<'view' | 'edit'>('view');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async () => {
    if (!memberId) return;
    setLoading(true);
    setSuccess(false);
    try {
      const response = await shareApi.createShare(taskId, { memberId, permission });
      if (response?.success) {
        setSuccess(true);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <h4 className="font-medium text-gray-900">分享给团队成员</h4>
      <div className="space-y-2">
        <input
          value={memberId}
          onChange={(event) => setMemberId(event.target.value)}
          placeholder="成员标识"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
        />
        <select
          value={permission}
          onChange={(event) => setPermission(event.target.value as 'view' | 'edit')}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
        >
          <option value="view">只读</option>
          <option value="edit">可编辑</option>
        </select>
      </div>
      <button
        onClick={handleSubmit}
        disabled={loading}
        className="px-3 py-2 text-sm text-white bg-primary-500 rounded-lg hover:bg-primary-600 disabled:opacity-50"
      >
        {loading ? '提交中' : '确认分享'}
      </button>
      {success && <p className="text-xs text-green-600">分享成功</p>}
    </div>
  );
};
