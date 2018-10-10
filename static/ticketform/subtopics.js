function refresh_subtopics() {
	var topic_id = $('#id_topic').val();
	var topic = topics_table[topic_id];
    if (topic_id == '') {
        $('#id_subtopic').html("<option value selected>---------</option>");
    }
    var subtopicsHtml = "<option value selected>---------</option>";
	for(var i = 0; i < topic.subtopic_set.length; i++)
	{
		var subtopic = topic.subtopic_set[i];
		subtopicsHtml += '<option value="' + subtopic.id + '">' + subtopic.display_name + '</option>';
	}
	$('#id_subtopic').html(subtopicsHtml);
	if($('#id_subtopic').html().includes(window.originallyCheckedTag))
		$('#id_subtopic').val(window.originallyCheckedTag);
	else
		$('#id_subtopic').val("");
}

$(document).ready(function() {
    window.originallyCheckedTag = $('#id_subtopic').val();
    $('#id_topic').change(refresh_subtopics);
    refresh_subtopics();
});