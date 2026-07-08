# Debug Session: thermal-low-recall
- **Status**: [OPEN]
- **Issue**: 热成像识别率仍然偏低，需要确认是模型出框低、输入预处理问题，还是时序/温度兜底判定问题。
- **Debug Server**: Pending
- **Log File**: .dbg/trae-debug-log-thermal-low-recall.ndjson

## Reproduction Steps
1. 运行 `dual_detect_service.py`
2. 让热成像视野内出现明显热源或人体/目标
3. 观察是否出现热成像框、是否进入对应报警分支

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | 热成像模型预处理与训练分布不匹配，导致高温目标也不出框 | High | Med | Pending |
| B | 热源面积太小或温度映射不合适，进入模型前特征被冲淡 | High | Med | Pending |
| C | 热成像有结果，但因分频/缓存/状态机时序被清空 | Med | Low | Pending |
| D | 原始温度矩阵已有明显高温，但温度兜底阈值或统计方式不适合当前传感器 | High | Low | Pending |

## Log Evidence
- Pending

## Verification Conclusion
- Pending
