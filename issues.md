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
- [ ] 11. when i ask for reminders at a specific time, it says 'i can remember but cant set a reminder for specifically 5pm' , is this intended??
- [ ] 12. i see a lot of errors in langfuse, lets pull all the errors traces and analyze them
