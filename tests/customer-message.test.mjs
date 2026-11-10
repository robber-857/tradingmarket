import test from 'node:test';
import assert from 'node:assert/strict';
import {customerMessage} from '../src/customer-message.js';

test('configuration, internal IDs and network diagnostics become customer messages', () => {
  for (const message of ['请在 .env 配置 OPENAI_API_KEY', '尚未配置 AI 翻译', 'snapshot ba2f3a832b653efc07d34456', 'Traceback: internal error']) {
    assert.equal(customerMessage(message), '服务暂时不可用，请稍后重试。');
  }
  assert.equal(customerMessage('Failed to fetch'), '暂时无法获取数据，请检查网络连接后重试。');
});
test('preserves useful input and evidence limitations', () => {
  for (const message of ['无风险利率必须在 0% 至 25% 之间。', '报价不足，无法计算隐含波动率。', '数据缺失不代表零。']) {
    assert.equal(customerMessage(message), message);
  }
});
test('gives recovery actions for expired data and rate limits', () => {
  assert.match(customerMessage('快照已过期'), /刷新后重新分析/);
  assert.match(customerMessage('429 rate limit'), /稍后重试/);
});
