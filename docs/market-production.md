# Market and Production Simulation

## Factory Type

The simulated factory is a general automotive-parts machining factory. Main
processes:

- turning
- milling
- grinding
- drilling
- inspection

## Product Categories

Product codes map to automotive machining parts:

- `A1`: 主轴 (main shaft)
- `A2`: 法兰盘 (flange)
- `A3`: 变速箱齿轮 (gearbox gear)
- `A4`: 精密轴套 (precision sleeve)
- `A5`: 转向连接件 (steering connector)

## Market Complexity

The virtual market has medium complexity:

- multiple product categories
- competitor price changes
- inventory pressure
- seasonal demand
- urgent upper-level allocation orders

## Planning Inputs

- market demand index
- current inventory
- workshop node health
- machine availability and tool wear level
- order deadline
- defect rate

## Planning Output

The production planner generates, per product:

- priority
- target quantity
- assigned process route
- assigned machine per route step (or `waiting-capacity` when blocked)
- risk reason

## Example

If `A1` (main shaft) demand rises while the turning workshop is healthy, the
planner raises the shaft target quantity and dispatches its route to turning
machines. If the turning node is isolated, those route steps become `blocked`
and the resource view reports the delivery risk.
