// Keep actionable research messages, but do not surface service setup/debug details.
export function customerMessage(value, fallback = '服务暂时不可用，请稍后重试。') {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) return fallback;
  if (/本周期.*额度已用完|请先登录|不属于当前账户|同一请求编号|等待恢复/.test(text)) return text;
  if (/快照.*(过期|不存在)|snapshot.*(expired|not found)/i.test(text))
    return '研究数据已更新或过期，请刷新后重新分析。';
  if (/429|rate.limit|额度|限流/i.test(text))
    return '请求较多，服务暂时繁忙，请稍后重试。';
  if (/API[_ ]?KEY|BEARER_TOKEN|SEC_USER_AGENT|\.env\b|npm run|Traceback|HTTPStatusError|localhost|127\.0\.0\.1|未配置|尚未配置|后端|接口权限|[a-f0-9]{24,}/i.test(text))
    return fallback;
  if (/Failed to fetch|NetworkError|fetch failed|Unexpected token|JSON|ECONN|ENOTFOUND|HTTP [45]\d\d/i.test(text))
    return '暂时无法获取数据，请检查网络连接后重试。';
  return text;
}
