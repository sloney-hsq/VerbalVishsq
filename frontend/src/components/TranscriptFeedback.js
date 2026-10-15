import { defineComponent, h } from "vue";

export const TranscriptFeedback = defineComponent({
  name: "TranscriptFeedback",
  props: {
    label: { type: String, required: true },
  },
  setup(props) {
    return () => h("span", { class: "transcript-feedback" }, props.label);
  },
});
