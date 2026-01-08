"use client"

import * as React from "react"
import { CalendarIcon } from 'lucide-react'
import { addDays, format } from "date-fns"
import { DateRange } from "react-day-picker"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

interface CalendarDateRangePickerProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: DateRange | undefined
  onDateChange?: (range: DateRange | undefined) => void
}

export function CalendarDateRangePicker({
                                          className,
                                          value,
                                          onDateChange,
                                          ...props
                                        }: CalendarDateRangePickerProps) {
  // If value not provided, fallback to an internal state default value
  const [internalValue, setInternalValue] = React.useState<DateRange | undefined>({
    from: new Date(2025, 0, 1),
    to: addDays(new Date(2025, 0, 1), 20),
  })

  const selectedValue = value ?? internalValue

  const handleSelect = (range: DateRange | undefined) => {
    if (onDateChange) {
      onDateChange(range)
    } else {
      setInternalValue(range)
    }
  }

  return (
      <div className={cn("grid gap-2", className)} {...props}>
        <Popover>
          <PopoverTrigger asChild>
            <Button
                id="date"
                variant={"outline"}
                className={cn(
                    "w-[260px] justify-start text-left font-normal",
                    !selectedValue && "text-muted-foreground"
                )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {selectedValue?.from ? (
                  selectedValue.to ? (
                      <>
                        {format(selectedValue.from, "LLL dd, y")} -{" "}
                        {format(selectedValue.to, "LLL dd, y")}
                      </>
                  ) : (
                      format(selectedValue.from, "LLL dd, y")
                  )
              ) : (
                  <span>Pick a date</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <Calendar
                initialFocus
                mode="range"
                defaultMonth={selectedValue?.from}
                selected={selectedValue}
                onSelect={handleSelect}
                numberOfMonths={2}
            />
          </PopoverContent>
        </Popover>
      </div>
  )
}
