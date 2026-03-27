# Issues

## Fixed

- [x] 1. new chat, have to scroll to bottom — fixed in d58a7b7 (auto-scroll on send)
- [x] 2. when i put enter and write multiple lines in the chat box, and send the message, the message which is displayed, dosnt have new lines in it — fixed in d58a7b7 (preserve newlines)
- [x] 6. for new users need some sort of intro or how to use when first log in happens — fixed in 55fe869 (onboarding hint: "pull down to see your plate")
- [x] 7. the landing page on phone dosnt fit on one page — fixed in 55fe869 (mobile spacing)
- [x] 9. on the chat text box, a rectangle appears sometimes — fixed in 55fe869 (focus ring CSS)
- [x] 10. before buttons appear beneath the message box for a second i can see the markdown code before its rendered into button — fixed (StreamingText action pattern stripping)
- [x] 13. when i reopen app and old messages open the option buttons beneath the text boxes are converted into markdown permanently — fixed (api.ts parseInlineActions on history load)
- [x] 14. when new users come, there is nothing telling them about the plate they can drag down and what does it do — fixed in 55fe869 (onboarding hint)
- [x] 15. on the plate, the time stamps shown along side tasks are messed up, they are in some code format — fixed (PlateItem.tsx formatDeadline)

## Open

- [x] 3. the 'your brain, but reliable' is okay or feels off?
- [x] 4. the plate pull down thing is hard to access as its small and sometimes goes away as i scroll up or down
- [x] 5. when does the plate gets updated?
- [ ] 8. audit the prompt of login demo and see if its correct, it should work for 2-3 prompts and then suggest the user to login, and it should show sign up and log in buttons below that suggestion message box
- [x] 11. when i ask for reminders at a specific time, it says 'i can remember but cant set a reminder for specifically 5pm' , is this intended?? — **Fixed in V2**: schedule_reminder tool added, LLM resolves natural language times
- [ ] 12. i see a lot of errors in langfuse, lets pull all the errors traces and analyze them

## AI issues (V2 Memory System fixes):

- [x] 1. Not associating date/time to memories, tasks, trackers — **Fixed**: Rich metadata extraction (logged_at on TRACKS_METRIC, temporal query_graph with date_from/date_to params)
- [x] 2. Past spending showing as open tasks on plate ("buy groceries", "buy loofah") — **Fixed**: Extraction now sets actionable=false for past-tense items, vw_actionable filters them out
- [x] 3. Meta-instructions showing on plate ("track spending"), stale reminders staying — **Fixed**: Meta-instructions return empty extraction, tiered expiry (routine deadlines expire at midnight, undated items expire after 14 days)
- [x] 4. Past-due time-specific tasks still suggested ("go to office" after morning) — **Fixed**: Agent system prompt instructs to skip items whose time-specific deadline has passed today, tiered expiry handles archival
- [x] 6. Reminders not working — **Fixed**: schedule_reminder tool using existing ScheduledAction + QStash infrastructure
