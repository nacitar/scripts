#!/usr/bin/env python2

def LoadCSV(filename):
    data, row, value = ([], [], '')
    # Open the file
    with open(filename,'rb') as handle:
        # Poor man's enum
        START, IN, END = range(3)
        quoteState = START
        # Process the file
        nextByte = handle.read(1)
        while True:
            byte = nextByte
            nextByte = handle.read(1)
            endOfRow = (byte in ['\r', '\n', ''])
            # Handle completed fields
            if quoteState != IN and (byte == ',' or endOfRow):
                # Add field
                row.append(value)
                # Reset state
                value = ''
                quoteState = START
                # Handle completed rows
                if endOfRow:
                    # Skip LF for DOS CRLF line endings
                    if byte == '\r' and nextByte == '\n':
                        nextByte = handle.read(1)
                    # Add row if not a blank line
                    if len(row) != 1 or row[0] != '':
                        data.append(row)
                    # Reset state
                    row = []
            # Handle quotes
            elif byte == '"':
                # Handle first occurrence of quoted text
                if quoteState != END:
                    # Handle consecutive quotes
                    if quoteState == IN and nextByte == '"':
                        # Add a literal quotation mark
                        value += '"'
                        # Skip next quote (already handled)
                        nextByte = handle.read(1)
                    # Advance quote state for starting/ending quotes.
                    elif quoteState == START:
                        quoteState = IN
                    elif quoteState == IN:
                        quoteState = END
                # Handle additional quoted strings
                else:
                    raise RuntimeError('Fields must be quoted in their'
                            ' entirety or not at all.')
            # Handle field data
            elif byte != '':
                # Advance quote state if first character is not a quote
                if quoteState == START:
                    # No quotes allowed if not the entire field
                    quoteState = END
                # Append to field data
                value += byte
            # Handle EOF
            if byte == '':
                # Detect unterminated quotes
                if quoteState == IN:
                    raise RuntimeError('Unterminated quote.')
                # Exit the loop
                break
    # Return the loaded data
    return data


def main():
    data = LoadCSV('input.csv')
    print "Data:"
    print data
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
