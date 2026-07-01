# Market and Production Simulation

## Factory Type

The simulated factory is a general machining factory. Main processes:

- turning
- milling
- grinding

## Product Categories

- `P1`: standard shaft parts
- `P2`: flanges
- `P3`: gear blanks
- `P4`: precision sleeves
- `P5`: custom connectors

## Market Complexity

The virtual market has medium complexity:

- multiple product categories
- competitor price changes
- inventory pressure
- seasonal demand
- urgent orders

## Planning Inputs

- market demand index
- current inventory
- workshop node health
- machine availability
- order deadline
- defect rate
- tool wear level

## Planning Output

The production planner should generate:

- product priority
- target quantity
- assigned workshop route
- estimated completion time
- risk reason

## Example

If standard shaft demand increases while turning workshop load is healthy, the
planner should increase shaft orders and assign more turning capacity. If the
turning node is isolated, the planner should reduce affected orders and report
delivery risk.
