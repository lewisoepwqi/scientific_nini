import React, { useState } from 'react';

const templateOptions = [
  { id: 'default', name: '默认模板' },
  { id: 'nature', name: 'Nature' },
  { id: 'science', name: 'Science' },
];

interface ExportTemplateSelectProps {
  onChange?: (templateId: string) => void;
}

export const ExportTemplateSelect: React.FC<ExportTemplateSelectProps> = ({ onChange }) => {
  const [selected, setSelected] = useState('default');

  const handleChange = (value: string) => {
    setSelected(value);
    onChange?.(value);
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
      <h4 className="font-medium text-gray-900">出版级模板</h4>
      <select
        value={selected}
        onChange={(event) => handleChange(event.target.value)}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
      >
        {templateOptions.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
      <p className="text-xs text-gray-500">选择模板后将自动应用规范校验。</p>
    </div>
  );
};
