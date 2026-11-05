# 形状名称与调整参数

使用形状调整参数或不熟悉的形状名称时，先读参数约定，再查目标形状行。元素字段定义见[形状类型](../technical.md#shape形状)；排版仍遵循[唯一风格](../style.md)。

## 参数约定

- `adjustments` 的顺序和数量遵循 OOXML。
- 数值通常在 [0, 100000]，表示比例，100000 对应 100%。
- OOXML 角度单位为 1/60000 度，换算为 `OOXML value = degrees × 60000`，例如 16200000 对应 270°。
- 数组必须完整，不能省略中间参数；也可整体省略以采用默认值。
- `-` 表示没有可调参数。

## 基本形状

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| rect | 矩形 | - | - |
| roundRect | 圆角矩形 | [圆角半径] | [16667] |
| ellipse | 椭圆 | - | - |
| triangle | 三角形 | [顶点水平位置] | [50000] |
| rtTriangle | 直角三角形 | - | - |
| parallelogram | 平行四边形 | [倾斜偏移] | [25000] |
| trapezoid | 梯形 | [上边内缩] | [25000] |
| nonIsoscelesTrapezoid | 不等腰梯形 | [左偏移, 右偏移] | [25000, 25000] |
| diamond | 菱形 | - | - |
| pentagon | 正五边形 | [水平因子, 垂直因子] | [105146, 110557] |
| hexagon | 六边形 | [内缩偏移, 垂直因子] | [25000, 115470] |
| heptagon | 七边形 | [水平因子, 垂直因子] | [102572, 105210] |
| octagon | 八边形 | [切角大小] | [29289] |
| decagon | 十边形 | [垂直因子] | [105146] |
| dodecagon | 十二边形 | - | - |
| plus | 加号 | [臂宽比例] | [25000] |
| homePlate | 五边箭头 | [箭头尖端偏移] | [50000] |
| chevron | V 形箭头 | [V 形尖端偏移] | [50000] |
| pie | 饼形 | [起始角°, 终止角°] | [0, 16200000] |
| pieWedge | 饼楔形 | - | - |
| arc | 弧形 | [起始角°, 终止角°] | [16200000, 0] |
| chord | 弦形 | [起始角°, 终止角°] | [2700000, 16200000] |
| blockArc | 块弧 | [起始角°, 终止角°, 厚度] | [10800000, 0, 25000] |
| teardrop | 泪滴形 | [尾部延伸比例] | [100000] |
| frame | 框 | [边框厚度] | [12500] |
| halfFrame | 半框 | [水平厚度, 垂直厚度] | [33333, 33333] |
| corner | 直角形 | [水平厚度, 垂直厚度] | [50000, 50000] |
| diagStripe | 斜条纹 | [条纹宽度] | [50000] |
| foldedCorner | 折角形 | - | - |
| donut | 圆环 | [环宽比例] | [25000] |
| noSmoking | 禁止符号 | [斜杠宽度] | [18750] |
| heart | 心形 | - | - |
| lightningBolt | 闪电 | - | - |
| sun | 太阳 | [光芒内半径比例] | [25000] |
| moon | 月亮 | [月牙宽度] | [50000] |
| cloud | 云形 | - | - |
| smileyFace | 笑脸 | [嘴部弯曲度] | [4653] |
| bevel | 棱台 | [斜面宽度] | [12500] |
| can | 圆柱 | [椭圆盖高度] | [25000] |
| cube | 立方体 | [透视深度] | [25000] |
| funnel | 漏斗 | - | - |
| gear6 | 六齿轮 | [齿高, 齿宽] | [15000, 3526] |
| gear9 | 九齿轮 | [齿高, 齿宽] | [10000, 1763] |
| plaque | 牌匾 | [圆角半径] | [16667] |
| doubleWave | 双波形 | [波幅, 水平偏移] | [6250, 0] |
| wave | 波形 | [波幅, 水平偏移] | [12500, 0] |
| lineInv | 反向直线 | - | - |

## 矩形变体

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| round1Rect | 单圆角矩形 | [圆角半径] | [16667] |
| round2DiagRect | 对角双圆角矩形 | [圆角 1 半径, 圆角 2 半径] | [16667, 0] |
| round2SameRect | 同侧双圆角矩形 | [上圆角半径, 下圆角半径] | [16667, 0] |
| snip1Rect | 单切角矩形 | [切角大小] | [16667] |
| snip2DiagRect | 对角双切角矩形 | [切角 1 大小, 切角 2 大小] | [0, 16667] |
| snip2SameRect | 同侧双切角矩形 | [上切角大小, 下切角大小] | [16667, 0] |
| snipRoundRect | 一圆角一切角矩形 | [圆角半径, 切角大小] | [16667, 16667] |

## 星形与爆炸形

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| star4 | 4 角星 | [内半径比例] | [12500] |
| star5 | 5 角星 | [内半径比例, 水平因子, 垂直因子] | [19098, 105146, 110557] |
| star6 | 6 角星 | [内半径比例, 水平因子] | [28868, 115470] |
| star7 | 7 角星 | [内半径比例, 水平因子, 垂直因子] | [34601, 102572, 105210] |
| star8 | 8 角星 | [内半径比例] | [37500] |
| star10 | 10 角星 | [内半径比例, 水平因子] | [42533, 105146] |
| star12 | 12 角星 | [内半径比例] | [37500] |
| star16 | 16 角星 | [内半径比例] | [37500] |
| star24 | 24 角星 | [内半径比例] | [37500] |
| star32 | 32 角星 | [内半径比例] | [37500] |
| irregularSeal1 | 爆炸形 1 | - | - |
| irregularSeal2 | 爆炸形 2 | - | - |

## 箭头

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| rightArrow | 右箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| leftArrow | 左箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| upArrow | 上箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| downArrow | 下箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| leftRightArrow | 左右箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| upDownArrow | 上下箭头 | [箭杆宽度, 上箭头长度, 箭杆宽度, 下箭头长度] | [50000, 50000, 50000, 50000] |
| quadArrow | 四向箭头 | [箭杆宽度, 箭头宽度, 箭头长度] | [22500, 22500, 22500] |
| leftRightUpArrow | 左、右、上箭头 | [箭杆宽度, 箭头宽度, 箭头长度] | [25000, 25000, 25000] |
| leftUpArrow | 左上箭头 | [箭杆宽度, 箭头宽度, 箭头长度] | [25000, 25000, 25000] |
| bentArrow | 折弯箭头 | [箭杆宽度, 箭头宽度, 箭头长度, 折弯位置] | [25000, 25000, 25000, 43750] |
| bentUpArrow | 上折箭头 | [箭杆宽度, 箭头宽度, 箭头长度] | [25000, 25000, 25000] |
| uturnArrow | 回转箭头 | [箭杆宽度, 箭头宽度, 箭头长度, 折弯半径, 箭杆长度] | [25000, 25000, 25000, 43750, 75000] |
| circularArrow | 环形箭头 | [箭头宽度, 起始角°, 终止角°, 弧角°, 箭尖宽度] | [12500, 1142319, 20457681, 10800000, 12500] |
| leftCircularArrow | 左环形箭头 | [箭头宽度, 起始角°, 终止角°, 弧角°, 箭尖宽度] | [12500, -1142319, 1142319, 10800000, 12500] |
| leftRightCircularArrow | 双向环形箭头 | [箭头宽度, 起始角°, 终止角°, 弧角°, 箭尖宽度] | [12500, 1142319, 20457681, 11942319, 12500] |
| curvedRightArrow | 右弧形箭头 | [箭头宽度, 弯曲度, 箭头长度] | [25000, 50000, 25000] |
| curvedLeftArrow | 左弧形箭头 | [箭头宽度, 弯曲度, 箭头长度] | [25000, 50000, 25000] |
| curvedUpArrow | 上弧形箭头 | [箭头宽度, 弯曲度, 箭头长度] | [25000, 50000, 25000] |
| curvedDownArrow | 下弧形箭头 | [箭头宽度, 弯曲度, 箭头长度] | [25000, 50000, 25000] |
| stripedRightArrow | 条纹右箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| notchedRightArrow | 缺口右箭头 | [箭杆宽度, 箭头长度] | [50000, 50000] |
| swooshArrow | 弯尾箭头 | [尾部宽度, 箭头长度] | [25000, 16667] |

## 箭头标注框

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| rightArrowCallout | 右箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框宽] | [25000, 25000, 25000, 64977] |
| leftArrowCallout | 左箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框宽] | [25000, 25000, 25000, 64977] |
| upArrowCallout | 上箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框高] | [25000, 25000, 25000, 64977] |
| downArrowCallout | 下箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框高] | [25000, 25000, 25000, 64977] |
| leftRightArrowCallout | 左右箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框宽] | [25000, 25000, 25000, 48123] |
| upDownArrowCallout | 上下箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框高] | [25000, 25000, 25000, 48123] |
| quadArrowCallout | 四向箭头标注框 | [箭杆宽度, 箭头宽度, 箭头长度, 框大小] | [18515, 18515, 18515, 48123] |

## 标注框

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| wedgeRectCallout | 矩形标注框 | [尖端 X 偏移, 尖端 Y 偏移] | [-20833, 62500] |
| wedgeRoundRectCallout | 圆角矩形标注框 | [尖端 X 偏移, 尖端 Y 偏移, 圆角半径] | [-20833, 62500, 16667] |
| wedgeEllipseCallout | 椭圆标注框 | [尖端 X 偏移, 尖端 Y 偏移] | [-20833, 62500] |
| cloudCallout | 云形标注框 | [尖端 X 偏移, 尖端 Y 偏移] | [-20833, 62500] |
| borderCallout1 | 线条标注 1 | [引出线 Y1, X1, Y2, X2] | [18750, -8333, 112500, -38333] |
| borderCallout2 | 线条标注 2 | [线条 Y1, X1, 折点 Y, X, 终点 Y, X] | [18750, -8333, 18750, -16667, 112500, -46667] |
| borderCallout3 | 线条标注 3 | [线条 Y1, X1, 折点 1 Y, X, 折点 2 Y, X, 终点 Y, X] | [18750, -8333, 18750, -16667, 100000, -16667, 112963, -8333] |
| accentCallout1 | 强调线条标注 1 | 同 borderCallout1 | [18750, -8333, 112500, -38333] |
| accentCallout2 | 强调线条标注 2 | 同 borderCallout2 | [18750, -8333, 18750, -16667, 112500, -46667] |
| accentCallout3 | 强调线条标注 3 | 同 borderCallout3 | [18750, -8333, 18750, -16667, 100000, -16667, 112963, -8333] |
| accentBorderCallout1 | 带边框强调线条标注 1 | 同 borderCallout1 | [18750, -8333, 112500, -38333] |
| accentBorderCallout2 | 带边框强调线条标注 2 | 同 borderCallout2 | [18750, -8333, 18750, -16667, 112500, -46667] |
| accentBorderCallout3 | 带边框强调线条标注 3 | 同 borderCallout3 | [18750, -8333, 18750, -16667, 100000, -16667, 112963, -8333] |
| callout1 | 无边框标注 1 | 同 borderCallout1 | [18750, -8333, 112500, -38333] |
| callout2 | 无边框标注 2 | 同 borderCallout2 | [18750, -8333, 18750, -16667, 112500, -46667] |
| callout3 | 无边框标注 3 | 同 borderCallout3 | [18750, -8333, 18750, -16667, 100000, -16667, 112963, -8333] |

> **标注尖端偏移：** X/Y 以形状中心为原点，按形状宽／高的比例表示；负值代表尖端在左侧／上方。

## 括号

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| leftBrace | 左大括号 | [弯曲度, 中点位置] | [8333, 50000] |
| rightBrace | 右大括号 | [弯曲度, 中点位置] | [8333, 50000] |
| leftBracket | 左方括号 | [弯曲度] | [8333] |
| rightBracket | 右方括号 | [弯曲度] | [8333] |
| bracePair | 大括号对 | [弯曲度] | [8333] |
| bracketPair | 方括号对 | [弯曲度] | [16667] |

## 缎带

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| ribbon | 下弯缎带 | [折叠高度, 缎带弯曲度] | [16667, 50000] |
| ribbon2 | 上弯缎带 | [折叠高度, 缎带弯曲度] | [16667, 50000] |
| ellipseRibbon | 曲面下缎带 | [弯曲度, 中部高度, 折叠高度] | [25000, 50000, 12500] |
| ellipseRibbon2 | 曲面上缎带 | [弯曲度, 中部高度, 折叠高度] | [25000, 50000, 12500] |
| leftRightRibbon | 左右缎带 | [折叠高度, 缎带弯曲度, 折叠宽度] | [50000, 50000, 16667] |

## 卷轴

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| horizontalScroll | 横卷轴 | [卷轴大小] | [12500] |
| verticalScroll | 竖卷轴 | [卷轴大小] | [12500] |

## 数学符号

| shapeName | 说明 | adjustments 参数 | 默认值 |
| --------- | --- | -------------- | ---- |
| mathPlus | 加号 | [线宽] | [23520] |
| mathMinus | 减号 | [线宽] | [23520] |
| mathMultiply | 乘号 | [线宽] | [23520] |
| mathDivide | 除号 | [线宽, 点间距, 点大小] | [23520, 5880, 11760] |
| mathEqual | 等号 | [线宽, 线间距] | [23520, 11760] |
| mathNotEqual | 不等号 | [线宽, 斜杠角°, 线间距] | [23520, 6600000, 11760] |

## 图表形状

| shapeName | 说明 |
| --------- | --- |
| chartPlus | 图表加号 |
| chartStar | 图表星号 |
| chartX | 图表 X |

## 标签形状

| shapeName | 说明 |
| --------- | --- |
| cornerTabs | 角标签 |
| squareTabs | 方标签 |
| plaqueTabs | 牌匾标签 |

## 动作按钮

| shapeName | 说明 |
| --------- | --- |
| actionButtonBackPrevious | 后退／上一页按钮 |
| actionButtonBeginning | 起始按钮 |
| actionButtonBlank | 空白按钮 |
| actionButtonDocument | 文档按钮 |
| actionButtonEnd | 结束按钮 |
| actionButtonForwardNext | 前进／下一页按钮 |
| actionButtonHelp | 帮助按钮 |
| actionButtonHome | 主页按钮 |
| actionButtonInformation | 信息按钮 |
| actionButtonMovie | 影片按钮 |
| actionButtonReturn | 返回按钮 |
| actionButtonSound | 声音按钮 |

## 流程图形状

| shapeName | 说明 |
| --------- | --- |
| flowChartProcess | 流程图： 处理 |
| flowChartAlternateProcess | 流程图： 备用处理 |
| flowChartDecision | 流程图： 判断 |
| flowChartDocument | 流程图： 文档 |
| flowChartMultidocument | 流程图： 多文档 |
| flowChartInputOutput | 流程图： 数据 |
| flowChartPredefinedProcess | 流程图： 预定义处理 |
| flowChartInternalStorage | 流程图： 内部存储 |
| flowChartManualInput | 流程图： 手动输入 |
| flowChartManualOperation | 流程图： 手动操作 |
| flowChartPreparation | 流程图： 准备 |
| flowChartDelay | 流程图： 延迟 |
| flowChartTerminator | 流程图： 终止符 |
| flowChartConnector | 流程图： 连接符 |
| flowChartOffpageConnector | 流程图： 跨页连接符 |
| flowChartPunchedCard | 流程图： 穿孔卡片 |
| flowChartPunchedTape | 流程图： 穿孔带 |
| flowChartCollate | 流程图： 整理 |
| flowChartSort | 流程图： 排序 |
| flowChartExtract | 流程图： 提取 |
| flowChartMerge | 流程图： 合并 |
| flowChartOr | 流程图： 或 |
| flowChartSummingJunction | 流程图： 求和连接点 |
| flowChartOnlineStorage | 流程图： 在线存储 |
| flowChartMagneticDisk | 流程图： 磁盘 |
| flowChartMagneticDrum | 流程图： 磁鼓 |
| flowChartMagneticTape | 流程图： 磁带 |
| flowChartOfflineStorage | 流程图： 离线存储 |
| flowChartDisplay | 流程图： 显示 |
