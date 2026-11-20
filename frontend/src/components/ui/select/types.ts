export interface SelectOption<T extends string = string> {
  value: T // never empty: reka-ui reserves '' for "no selection"
  label: string
}
