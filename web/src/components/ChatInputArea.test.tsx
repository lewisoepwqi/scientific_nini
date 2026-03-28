import { describe, expect, it, vi } from "vitest";

vi.mock("../store", () => ({
 useStore: vi.fn(),
}));

vi.mock("../store/confirm-store", () => ({
 useConfirm: vi.fn(),
}));

vi.mock("../store/onboard-store", () => ({
 useOnboardStore: vi.fn(),
}));

vi.mock("./FileUpload", () => ({
 default: () => null,
}));

vi.mock("./ModelSelector", () => ({
 default: () => null,
}));

vi.mock("./ui/Button", () => ({
 default: () => null,
}));

vi.mock("lucide-react", () => ({
 Archive: () => null,
 Send: () => null,
 Square: () => null,
}));

import { computeUsageRatio } from "./ChatInputArea";

describe("computeUsageRatio", () => {
 it("应按压缩阈值返回真实占用比例", () => {
 expect(computeUsageRatio(3000, 30000)).toBeCloseTo(0.1);
 expect(computeUsageRatio(15000, 30000)).toBeCloseTo(0.5);
 });

 it("应在阈值无效或超出上限时进行裁剪", () => {
 expect(computeUsageRatio(100, 0)).toBe(0);
 expect(computeUsageRatio(45000, 30000)).toBe(1);
 });
});
