# A/B `v03` — 조건별 평균 ± 표준편차(모집단 sd), 반복 n

> 생성: `python3 analysis/ab_run.py --exp v03 --summarize-only` · TC L-20,Y-24,L-60,L-40,Y-07-b,L-23,L-33,L-32 · sim=scripted · judge on

| 조건 | env | n | ok | partial | fail | required_recall | must_say_rate | forbidden | off_target | premature | avg_bubbles_per_case | avg_chars_per_bubble | over_500 | p50_ms | p95_ms | p95_turn_ms | max_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| default | `{}` | 2 | 6.5±0.5 | 1.5±0.5 | 0±0.0 | 1.0±0.0 | 0.932±0.013 | 0±0.0 | 0±0.0 | 0±0.0 | 3.565±0.315 | 198.1±0.4 | 0±0.0 | 5015±203.0 | 12208.5±163.5 | 12208.5±163.5 | 15853±3541.0 |
| t120 | `{"AGENT_TARGET_CHARS": "120"}` | 2 | 8±0.0 | 0±0.0 | 0±0.0 | 1.0±0.0 | 0.973±0.0 | 0±0.0 | 0±0.0 | 0±0.0 | 3.38±0.0 | 195.05±4.05 | 0±0.0 | 5002±47.0 | 13433±310.0 | 13433±310.0 | 13963±1.0 |
