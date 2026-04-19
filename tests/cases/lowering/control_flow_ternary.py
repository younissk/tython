i = 0
while i < 5:
    i = i + 1
    if i == 2:
        continue
    elif i == 4:
        break
    else:
        pass
label = "done" if i > 0 else "start"
