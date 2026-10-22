import sys


class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None
        self.tail = None

    def insert(self, value):
        node = Node(value)
        if self.head is None:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node

    def delete(self, value):
        prev, cur = None, self.head
        while cur is not None and cur.value != value:
            prev, cur = cur, cur.next
        if cur is None:
            return
        if prev is None:
            self.head = cur.next
        else:
            prev.next = cur.next
        if cur is self.tail:
            self.tail = prev

    def search(self, value):
        cur = self.head
        while cur is not None:
            if cur.value == value:
                return True
            cur = cur.next
        return False

    def display(self):
        parts = []
        cur = self.head
        while cur is not None:
            parts.append(str(cur.value))
            cur = cur.next
        parts.append("None")
        return " -> ".join(parts)


def main():
    linked_list = LinkedList()
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        command = parts[0]
        if command == "insert":
            linked_list.insert(int(parts[1]))
        elif command == "delete":
            linked_list.delete(int(parts[1]))
        elif command == "search":
            print("Found" if linked_list.search(int(parts[1])) else "Not Found")
        elif command == "display":
            print(linked_list.display())


if __name__ == "__main__":
    main()
